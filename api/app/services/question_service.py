"""Question processing service with automated execution and multi-LLM support."""

import asyncio
import csv
import json
import time
from datetime import datetime, timedelta
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from app.core.config import Settings
from app.core.logging import get_logger
from app.integrations.anythingllm_client import (
    AnythingLLMClient,
    AnythingLLMError,
    MessageError,
    ThreadError,
    WorkspaceNotFoundError,
)
from app.models.pydantic_models import (
    Job,
    JobCreate,
    JobResponse,
    JobStatus,
    JobType,
    LLMConfig,
    LLMProvider,
    Question,
    QuestionCreate,
    QuestionRequest,
    QuestionResult,
    QuestionResults,
)
from app.repositories.job_repository import JobRepository

logger = get_logger(__name__)


class ExportFormat(str, Enum):
    """Export format enumeration."""
    JSON = "json"
    CSV = "csv"


class QuestionProcessingError(Exception):
    """Question processing error."""
    pass


class ThreadManagementError(QuestionProcessingError):
    """Thread management error."""
    pass


class ConfidenceCalculationError(QuestionProcessingError):
    """Confidence calculation error."""
    pass


class ExportError(QuestionProcessingError):
    """Export error."""
    pass


class DocumentTypeRouter:
    """Routes questions based on document types."""
    
    # Document type mappings for routing
    DOCUMENT_TYPE_KEYWORDS = {
        "contract": ["contract", "agreement", "terms", "conditions", "legal"],
        "financial": ["financial", "budget", "cost", "price", "payment", "invoice"],
        "technical": ["technical", "specification", "requirement", "design"],
        "procurement": ["procurement", "vendor", "supplier", "bid", "proposal"],
        "compliance": ["compliance", "regulation", "policy", "standard", "audit"],
    }
    
    def __init__(self):
        """Initialize document type router."""
        self.logger = get_logger(f"{__name__}.DocumentTypeRouter")
    
    def route_question_by_document_type(
        self, 
        question: Question, 
        available_doc_types: List[str]
    ) -> str:
        """
        Route question to appropriate document type based on content analysis.
        
        Args:
            question: Question to route
            available_doc_types: Available document types in workspace
            
        Returns:
            Best matching document type or "general" if no specific match
        """
        question_text = question.text.lower()
        
        # Score each document type based on keyword matches
        type_scores = {}
        
        for doc_type in available_doc_types:
            score = 0
            keywords = self.DOCUMENT_TYPE_KEYWORDS.get(doc_type.lower(), [])
            
            for keyword in keywords:
                if keyword in question_text:
                    score += 1
            
            if score > 0:
                type_scores[doc_type] = score
        
        # Return highest scoring type or "general"
        if type_scores:
            best_type = max(type_scores.items(), key=lambda x: x[1])[0]
            self.logger.debug(
                f"Routed question to document type '{best_type}' "
                f"with score {type_scores[best_type]}"
            )
            return best_type
        
        self.logger.debug("No specific document type match, using 'general'")
        return "general"


class ConfidenceCalculator:
    """Calculates confidence scores for question responses."""
    
    def __init__(self):
        """Initialize confidence calculator."""
        self.logger = get_logger(f"{__name__}.ConfidenceCalculator")
    
    def calculate_confidence_score(
        self, 
        response: str, 
        expected_fragments: List[str]
    ) -> Tuple[float, List[str]]:
        """
        Calculate confidence score based on expected fragments found in response.
        
        Args:
            response: LLM response text
            expected_fragments: List of expected text fragments
            
        Returns:
            Tuple of (confidence_score, found_fragments)
        """
        if not expected_fragments:
            # If no expected fragments, use response quality heuristics
            return self._calculate_heuristic_confidence(response), []
        
        response_lower = response.lower()
        found_fragments = []
        
        # Check for exact matches of expected fragments
        for fragment in expected_fragments:
            if fragment.lower() in response_lower:
                found_fragments.append(fragment)
        
        # Calculate base confidence from fragment matches
        fragment_confidence = len(found_fragments) / len(expected_fragments)
        
        # Apply response quality modifiers
        quality_modifier = self._calculate_quality_modifier(response)
        
        # Combine scores (weighted average)
        final_confidence = (fragment_confidence * 0.7) + (quality_modifier * 0.3)
        
        # Ensure confidence is between 0 and 1
        final_confidence = max(0.0, min(1.0, final_confidence))
        
        self.logger.debug(
            f"Calculated confidence: {final_confidence:.3f} "
            f"(fragments: {len(found_fragments)}/{len(expected_fragments)}, "
            f"quality: {quality_modifier:.3f})"
        )
        
        return final_confidence, found_fragments
    
    def _calculate_heuristic_confidence(self, response: str) -> float:
        """
        Calculate confidence based on response quality heuristics.
        
        Args:
            response: LLM response text
            
        Returns:
            Confidence score between 0 and 1
        """
        if not response or not response.strip():
            return 0.0
        
        response = response.strip()
        
        # Length-based scoring (reasonable length indicates better response)
        length_score = min(len(response) / 500, 1.0)  # Normalize to 500 chars
        
        # Structure-based scoring (sentences, punctuation)
        sentence_count = len([s for s in response.split('.') if s.strip()])
        structure_score = min(sentence_count / 3, 1.0)  # Normalize to 3 sentences
        
        # Content quality indicators
        quality_indicators = [
            "specific", "detailed", "according to", "based on", "document",
            "shows", "indicates", "states", "mentions", "contains"
        ]
        
        quality_score = 0.0
        for indicator in quality_indicators:
            if indicator in response.lower():
                quality_score += 0.1
        
        quality_score = min(quality_score, 1.0)
        
        # Negative indicators (uncertainty, lack of information)
        negative_indicators = [
            "i don't know", "not sure", "unclear", "cannot determine",
            "no information", "not specified", "unable to find"
        ]
        
        negative_penalty = 0.0
        for indicator in negative_indicators:
            if indicator in response.lower():
                negative_penalty += 0.2
        
        # Combine scores
        heuristic_confidence = (
            (length_score * 0.3) + 
            (structure_score * 0.3) + 
            (quality_score * 0.4)
        ) - negative_penalty
        
        return max(0.0, min(1.0, heuristic_confidence))
    
    def _calculate_quality_modifier(self, response: str) -> float:
        """
        Calculate quality modifier based on response characteristics.
        
        Args:
            response: LLM response text
            
        Returns:
            Quality modifier between 0 and 1
        """
        return self._calculate_heuristic_confidence(response)


class QuestionService:
    """Service for automated question processing and execution."""
    
    def __init__(
        self,
        settings: Settings,
        job_repository: JobRepository,
        anythingllm_client: AnythingLLMClient,
    ):
        """
        Initialize question service.
        
        Args:
            settings: Application settings
            job_repository: Job repository for tracking operations
            anythingllm_client: AnythingLLM integration client
        """
        self.settings = settings
        self.job_repository = job_repository
        self.anythingllm_client = anythingllm_client
        
        # Initialize helper components
        self.document_router = DocumentTypeRouter()
        self.confidence_calculator = ConfidenceCalculator()
        
        # Processing configuration
        self.default_max_concurrent = 3
        self.default_timeout = 300  # 5 minutes
        self.max_questions_per_request = 50
        
        logger.info("Initialized QuestionService")
    
    async def execute_questions(self, request: QuestionRequest) -> JobResponse:
        """
        Execute automated question sets against workspace.
        
        Args:
            request: Question execution request
            
        Returns:
            Job response with processing status
            
        Raises:
            QuestionProcessingError: If execution initiation fails
        """
        logger.info(
            f"Starting question execution for workspace {request.workspace_id} "
            f"with {len(request.questions)} questions"
        )
        
        try:
            # Validate request
            await self._validate_question_request(request)
            
            # Create job for tracking
            job_metadata = {
                "workspace_id": request.workspace_id,
                "question_count": len(request.questions),
                "max_concurrent": request.max_concurrent,
                "timeout": request.timeout,
                "llm_config": request.llm_config.model_dump() if request.llm_config else None,
            }
            
            job = await self.job_repository.create_job(
                job_type=JobType.QUESTION_PROCESSING,
                workspace_id=request.workspace_id,
                metadata=job_metadata
            )
            
            # Start background processing
            asyncio.create_task(
                self._process_questions_async(job.id, request)
            )
            
            logger.info(
                f"Created question processing job {job.id} "
                f"for workspace {request.workspace_id}"
            )
            
            return JobResponse(
                job=job,
                links={
                    "status": f"/api/v1/questions/jobs/{job.id}",
                    "results": f"/api/v1/questions/jobs/{job.id}/results",
                },
                estimated_completion=datetime.utcnow() + timedelta(seconds=request.timeout)
            )
            
        except Exception as e:
            logger.error(f"Failed to initiate question execution: {e}")
            raise QuestionProcessingError(f"Failed to initiate execution: {e}")
    
    async def _validate_question_request(self, request: QuestionRequest) -> None:
        """
        Validate question execution request.
        
        Args:
            request: Question request to validate
            
        Raises:
            QuestionProcessingError: If validation fails
        """
        # Check workspace exists
        try:
            await self.anythingllm_client.get_workspace(request.workspace_id)
        except WorkspaceNotFoundError:
            raise QuestionProcessingError(f"Workspace not found: {request.workspace_id}")
        except AnythingLLMError as e:
            raise QuestionProcessingError(f"Workspace validation failed: {e}")
        
        # Validate question count
        if len(request.questions) > self.max_questions_per_request:
            raise QuestionProcessingError(
                f"Too many questions: {len(request.questions)} "
                f"(max: {self.max_questions_per_request})"
            )
        
        # Validate LLM configurations
        if request.llm_config:
            self._validate_llm_config(request.llm_config)
        
        for question in request.questions:
            if question.llm_config:
                self._validate_llm_config(question.llm_config)
    
    def _validate_llm_config(self, llm_config: LLMConfig) -> None:
        """
        Validate LLM configuration.
        
        Args:
            llm_config: LLM configuration to validate
            
        Raises:
            QuestionProcessingError: If configuration is invalid
        """
        # Validate provider
        if llm_config.provider not in LLMProvider:
            raise QuestionProcessingError(f"Unsupported LLM provider: {llm_config.provider}")
        
        # Validate model name
        if not llm_config.model.strip():
            raise QuestionProcessingError("LLM model name cannot be empty")
        
        # Validate temperature
        if not (0.0 <= llm_config.temperature <= 2.0):
            raise QuestionProcessingError(
                f"Invalid temperature: {llm_config.temperature} (must be 0.0-2.0)"
            )
        
        # Validate timeout
        if not (1 <= llm_config.timeout <= 300):
            raise QuestionProcessingError(
                f"Invalid timeout: {llm_config.timeout} (must be 1-300 seconds)"
            )
    
    async def _process_questions_async(
        self,
        job_id: str,
        request: QuestionRequest
    ) -> None:
        """
        Process questions asynchronously in background.
        
        Args:
            job_id: Job ID for tracking
            request: Question execution request
        """
        try:
            # Update job status to processing
            await self.job_repository.update_job_status(
                job_id=job_id,
                status=JobStatus.PROCESSING,
                progress=0.0
            )
            
            # Process question set
            results = await self.process_question_set(
                questions=[Question(**q.model_dump()) for q in request.questions],
                workspace_id=request.workspace_id,
                default_llm_config=request.llm_config,
                max_concurrent=request.max_concurrent,
                timeout=request.timeout,
                job_id=job_id
            )
            
            # Calculate summary statistics
            summary = self._calculate_results_summary(results)
            
            # Update job with final result
            await self.job_repository.update_job_status(
                job_id=job_id,
                status=JobStatus.COMPLETED,
                progress=100.0,
                result={
                    "results": [r.model_dump() for r in results.results],
                    "summary": summary,
                    "total_questions": results.total_questions,
                    "successful_questions": results.successful_questions,
                    "failed_questions": results.failed_questions,
                    "total_processing_time": results.total_processing_time,
                    "average_confidence": results.average_confidence,
                }
            )
            
            logger.info(
                f"Successfully completed question processing job {job_id} "
                f"({results.successful_questions}/{results.total_questions} successful)"
            )
            
        except Exception as e:
            logger.error(f"Error in background question processing for job {job_id}: {e}")
            try:
                await self.job_repository.update_job_status(
                    job_id=job_id,
                    status=JobStatus.FAILED,
                    progress=0.0,
                    error=f"Processing error: {str(e)}"
                )
            except Exception as update_error:
                logger.error(f"Failed to update job status after error: {update_error}")
    
    async def process_question_set(
        self,
        questions: List[Question],
        workspace_id: str,
        default_llm_config: Optional[LLMConfig] = None,
        max_concurrent: int = 3,
        timeout: int = 300,
        job_id: Optional[str] = None
    ) -> QuestionResults:
        """
        Process a set of questions with concurrent execution.
        
        Args:
            questions: List of questions to process
            workspace_id: Target workspace ID
            default_llm_config: Default LLM configuration
            max_concurrent: Maximum concurrent questions
            timeout: Total timeout in seconds
            job_id: Optional job ID for progress tracking
            
        Returns:
            Question execution results
            
        Raises:
            QuestionProcessingError: If processing fails
        """
        logger.info(
            f"Processing {len(questions)} questions for workspace {workspace_id} "
            f"with max_concurrent={max_concurrent}"
        )
        
        start_time = time.time()
        
        try:
            # Create thread for question processing
            thread_info = await self.create_thread(
                workspace_id=workspace_id,
                name=f"Question Processing {uuid4().hex[:8]}"
            )
            
            try:
                # Process questions concurrently
                results = await self.manage_concurrent_processing(
                    questions=questions,
                    workspace_id=workspace_id,
                    thread_id=thread_info.id,
                    default_llm_config=default_llm_config,
                    max_concurrent=max_concurrent,
                    timeout=timeout,
                    job_id=job_id
                )
                
                # Calculate processing statistics
                total_time = time.time() - start_time
                successful_count = sum(1 for r in results if r.success)
                failed_count = len(results) - successful_count
                
                # Calculate average confidence
                confidence_scores = [r.confidence_score for r in results if r.success]
                avg_confidence = (
                    sum(confidence_scores) / len(confidence_scores)
                    if confidence_scores else 0.0
                )
                
                # Create results object
                question_results = QuestionResults(
                    job_id=job_id or str(uuid4()),
                    workspace_id=workspace_id,
                    results=results,
                    summary=self._calculate_results_summary(results),
                    total_questions=len(questions),
                    successful_questions=successful_count,
                    failed_questions=failed_count,
                    total_processing_time=total_time,
                    average_confidence=avg_confidence
                )
                
                logger.info(
                    f"Completed question processing: {successful_count}/{len(questions)} "
                    f"successful in {total_time:.2f}s"
                )
                
                return question_results
                
            finally:
                # Clean up thread
                await self.cleanup_threads(workspace_id, [thread_info.id])
                
        except Exception as e:
            logger.error(f"Error processing question set: {e}")
            raise QuestionProcessingError(f"Question processing failed: {e}")
    
    def _calculate_results_summary(self, results: List[QuestionResult]) -> Dict[str, Any]:
        """
        Calculate summary statistics for question results.
        
        Args:
            results: List of question results
            
        Returns:
            Summary statistics dictionary
        """
        if not results:
            return {
                "total_questions": 0,
                "successful_questions": 0,
                "failed_questions": 0,
                "success_rate": 0.0,
                "average_confidence": 0.0,
                "average_processing_time": 0.0,
                "confidence_distribution": {},
                "error_types": {}
            }
        
        successful_results = [r for r in results if r.success]
        failed_results = [r for r in results if not r.success]
        
        # Calculate confidence distribution
        confidence_ranges = {
            "high (0.8-1.0)": 0,
            "medium (0.5-0.8)": 0,
            "low (0.0-0.5)": 0
        }
        
        for result in successful_results:
            if result.confidence_score >= 0.8:
                confidence_ranges["high (0.8-1.0)"] += 1
            elif result.confidence_score >= 0.5:
                confidence_ranges["medium (0.5-0.8)"] += 1
            else:
                confidence_ranges["low (0.0-0.5)"] += 1
        
        # Analyze error types
        error_types = {}
        for result in failed_results:
            if result.error:
                error_type = result.error.split(":")[0] if ":" in result.error else "Unknown"
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        return {
            "total_questions": len(results),
            "successful_questions": len(successful_results),
            "failed_questions": len(failed_results),
            "success_rate": len(successful_results) / len(results) * 100,
            "average_confidence": (
                sum(r.confidence_score for r in successful_results) / len(successful_results)
                if successful_results else 0.0
            ),
            "average_processing_time": (
                sum(r.processing_time for r in results) / len(results)
            ),
            "confidence_distribution": confidence_ranges,
            "error_types": error_types
        }

    async def create_thread(self, workspace_id: str, name: str) -> Any:
        """
        Create a new thread in workspace for question processing.
        
        Args:
            workspace_id: Target workspace ID
            name: Thread name
            
        Returns:
            Thread information
            
        Raises:
            ThreadManagementError: If thread creation fails
        """
        logger.debug(f"Creating thread '{name}' in workspace {workspace_id}")
        
        try:
            thread_response = await self.anythingllm_client.create_thread(
                workspace_id=workspace_id,
                name=name
            )
            
            logger.debug(f"Created thread {thread_response.thread.id} in workspace {workspace_id}")
            return thread_response.thread
            
        except ThreadError as e:
            logger.error(f"Failed to create thread in workspace {workspace_id}: {e}")
            raise ThreadManagementError(f"Thread creation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error creating thread: {e}")
            raise ThreadManagementError(f"Unexpected thread creation error: {e}")
    
    async def manage_concurrent_processing(
        self,
        questions: List[Question],
        workspace_id: str,
        thread_id: str,
        default_llm_config: Optional[LLMConfig] = None,
        max_concurrent: int = 3,
        timeout: int = 300,
        job_id: Optional[str] = None
    ) -> List[QuestionResult]:
        """
        Manage concurrent question processing with thread management.
        
        Args:
            questions: List of questions to process
            workspace_id: Target workspace ID
            thread_id: Thread ID for processing
            default_llm_config: Default LLM configuration
            max_concurrent: Maximum concurrent questions
            timeout: Total timeout in seconds
            job_id: Optional job ID for progress tracking
            
        Returns:
            List of question results
            
        Raises:
            QuestionProcessingError: If concurrent processing fails
        """
        logger.info(
            f"Starting concurrent processing of {len(questions)} questions "
            f"with max_concurrent={max_concurrent}"
        )
        
        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []
        
        # Create tasks for all questions
        tasks = []
        for i, question in enumerate(questions):
            task = asyncio.create_task(
                self._process_single_question_with_semaphore(
                    semaphore=semaphore,
                    question=question,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    default_llm_config=default_llm_config,
                    question_index=i,
                    total_questions=len(questions),
                    job_id=job_id
                )
            )
            tasks.append(task)
        
        try:
            # Wait for all tasks to complete with timeout
            completed_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
            # Process results and handle exceptions
            for i, result in enumerate(completed_results):
                if isinstance(result, Exception):
                    logger.error(f"Question {i} failed with exception: {result}")
                    # Create error result
                    error_result = QuestionResult(
                        question_id=questions[i].id,
                        question_text=questions[i].text,
                        response="",
                        confidence_score=0.0,
                        processing_time=0.0,
                        fragments_found=[],
                        success=False,
                        error=f"Processing exception: {str(result)}"
                    )
                    results.append(error_result)
                else:
                    results.append(result)
            
            logger.info(
                f"Completed concurrent processing: "
                f"{sum(1 for r in results if r.success)}/{len(results)} successful"
            )
            
            return results
            
        except asyncio.TimeoutError:
            logger.error(f"Question processing timed out after {timeout} seconds")
            
            # Cancel remaining tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            # Create timeout results for incomplete questions
            for i, question in enumerate(questions):
                if i >= len(results):
                    timeout_result = QuestionResult(
                        question_id=question.id,
                        question_text=question.text,
                        response="",
                        confidence_score=0.0,
                        processing_time=timeout,
                        fragments_found=[],
                        success=False,
                        error=f"Processing timed out after {timeout} seconds"
                    )
                    results.append(timeout_result)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in concurrent question processing: {e}")
            raise QuestionProcessingError(f"Concurrent processing failed: {e}")
    
    async def _process_single_question_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        question: Question,
        workspace_id: str,
        thread_id: str,
        default_llm_config: Optional[LLMConfig] = None,
        question_index: int = 0,
        total_questions: int = 1,
        job_id: Optional[str] = None
    ) -> QuestionResult:
        """
        Process single question with semaphore for concurrency control.
        
        Args:
            semaphore: Semaphore for concurrency control
            question: Question to process
            workspace_id: Target workspace ID
            thread_id: Thread ID for processing
            default_llm_config: Default LLM configuration
            question_index: Index of current question
            total_questions: Total number of questions
            job_id: Optional job ID for progress tracking
            
        Returns:
            Question result
        """
        async with semaphore:
            try:
                # Update progress if job tracking is enabled
                if job_id:
                    progress = (question_index / total_questions) * 90.0  # Leave 10% for finalization
                    await self.job_repository.update_job_status(
                        job_id=job_id,
                        status=JobStatus.PROCESSING,
                        progress=progress
                    )
                
                # Process the question
                result = await self.run_single_question(
                    question=question,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    llm_config=question.llm_config or default_llm_config
                )
                
                logger.debug(
                    f"Processed question {question_index + 1}/{total_questions}: "
                    f"success={result.success}, confidence={result.confidence_score:.3f}"
                )
                
                return result
                
            except Exception as e:
                logger.error(f"Error processing question {question_index + 1}: {e}")
                return QuestionResult(
                    question_id=question.id,
                    question_text=question.text,
                    response="",
                    confidence_score=0.0,
                    processing_time=0.0,
                    fragments_found=[],
                    success=False,
                    error=f"Processing error: {str(e)}"
                )
    
    async def run_single_question(
        self,
        question: Question,
        workspace_id: str,
        thread_id: str,
        llm_config: Optional[LLMConfig] = None
    ) -> QuestionResult:
        """
        Run a single question and return result with confidence scoring.
        
        Args:
            question: Question to process
            workspace_id: Target workspace ID
            thread_id: Thread ID for processing
            llm_config: Optional LLM configuration override
            
        Returns:
            Question result with confidence score
            
        Raises:
            QuestionProcessingError: If question processing fails
        """
        logger.debug(f"Running question: {question.text[:100]}...")
        
        start_time = time.time()
        
        try:
            # Send message to thread
            message_response = await self.anythingllm_client.send_message(
                workspace_id=workspace_id,
                thread_id=thread_id,
                message=question.text,
                mode="query"
            )
            
            processing_time = time.time() - start_time
            
            # Calculate confidence score
            confidence_score, found_fragments = (
                self.confidence_calculator.calculate_confidence_score(
                    response=message_response.response,
                    expected_fragments=question.expected_fragments
                )
            )
            
            # Create successful result
            result = QuestionResult(
                question_id=question.id,
                question_text=question.text,
                response=message_response.response,
                confidence_score=confidence_score,
                processing_time=processing_time,
                fragments_found=found_fragments,
                success=True,
                metadata={
                    "message_id": message_response.id,
                    "chat_id": message_response.chatId,
                    "sources": message_response.sources,
                    "llm_config": llm_config.model_dump() if llm_config else None,
                }
            )
            
            logger.debug(
                f"Successfully processed question in {processing_time:.2f}s "
                f"with confidence {confidence_score:.3f}"
            )
            
            return result
            
        except MessageError as e:
            processing_time = time.time() - start_time
            logger.error(f"Message error for question: {e}")
            
            return QuestionResult(
                question_id=question.id,
                question_text=question.text,
                response="",
                confidence_score=0.0,
                processing_time=processing_time,
                fragments_found=[],
                success=False,
                error=f"Message error: {str(e)}"
            )
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(f"Unexpected error processing question: {e}")
            
            return QuestionResult(
                question_id=question.id,
                question_text=question.text,
                response="",
                confidence_score=0.0,
                processing_time=processing_time,
                fragments_found=[],
                success=False,
                error=f"Unexpected error: {str(e)}"
            )
    
    def route_question_by_document_type(
        self, 
        question: Question, 
        doc_types: List[str]
    ) -> str:
        """
        Route question to appropriate document type.
        
        Args:
            question: Question to route
            doc_types: Available document types
            
        Returns:
            Best matching document type
        """
        return self.document_router.route_question_by_document_type(question, doc_types)
    
    def calculate_confidence_score(
        self, 
        response: str, 
        expected_fragments: List[str]
    ) -> Tuple[float, List[str]]:
        """
        Calculate confidence score for response.
        
        Args:
            response: LLM response
            expected_fragments: Expected text fragments
            
        Returns:
            Tuple of (confidence_score, found_fragments)
        """
        return self.confidence_calculator.calculate_confidence_score(
            response, expected_fragments
        )
    
    async def cleanup_threads(
        self, 
        workspace_id: str, 
        thread_ids: List[str]
    ) -> bool:
        """
        Clean up threads after processing.
        
        Args:
            workspace_id: Workspace ID
            thread_ids: List of thread IDs to clean up
            
        Returns:
            True if cleanup successful
        """
        logger.debug(f"Cleaning up {len(thread_ids)} threads in workspace {workspace_id}")
        
        cleanup_success = True
        
        for thread_id in thread_ids:
            try:
                # Note: AnythingLLM client doesn't have explicit thread deletion
                # This is a placeholder for future implementation
                logger.debug(f"Thread {thread_id} cleanup completed")
                
            except Exception as e:
                logger.warning(f"Failed to cleanup thread {thread_id}: {e}")
                cleanup_success = False
        
        return cleanup_success
    
    async def export_results(
        self, 
        job_id: str, 
        format: ExportFormat
    ) -> Dict[str, Any]:
        """
        Export question results in specified format.
        
        Args:
            job_id: Job ID containing results
            format: Export format (JSON or CSV)
            
        Returns:
            Export data dictionary
            
        Raises:
            ExportError: If export fails
        """
        logger.info(f"Exporting results for job {job_id} in {format} format")
        
        try:
            # Get job with results
            job = await self.job_repository.get_job_with_results(job_id)
            if not job:
                raise ExportError(f"Job not found: {job_id}")
            
            if job.type != JobType.QUESTION_PROCESSING:
                raise ExportError(f"Job {job_id} is not a question processing job")
            
            if not job.result:
                raise ExportError(f"Job {job_id} has no results to export")
            
            # Extract results from job
            results_data = job.result.get("results", [])
            if not results_data:
                raise ExportError(f"No question results found in job {job_id}")
            
            # Convert to QuestionResult objects
            results = [QuestionResult(**result_data) for result_data in results_data]
            
            # Export in requested format
            if format == ExportFormat.JSON:
                export_data = await self._export_results_json(job, results)
            elif format == ExportFormat.CSV:
                export_data = await self._export_results_csv(job, results)
            else:
                raise ExportError(f"Unsupported export format: {format}")
            
            logger.info(f"Successfully exported {len(results)} results in {format} format")
            
            return export_data
            
        except ExportError:
            raise
        except Exception as e:
            logger.error(f"Error exporting results for job {job_id}: {e}")
            raise ExportError(f"Export failed: {str(e)}")
    
    async def _export_results_json(
        self, 
        job: Job, 
        results: List[QuestionResult]
    ) -> Dict[str, Any]:
        """
        Export results in JSON format.
        
        Args:
            job: Job containing results
            results: List of question results
            
        Returns:
            JSON export data
        """
        export_data = {
            "export_info": {
                "job_id": job.id,
                "workspace_id": job.workspace_id,
                "export_format": "json",
                "export_timestamp": datetime.utcnow().isoformat(),
                "total_results": len(results)
            },
            "job_metadata": {
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "processing_time_seconds": job.duration_seconds,
                "status": job.status,
                "metadata": job.metadata
            },
            "summary": job.result.get("summary", {}),
            "results": [result.model_dump() for result in results]
        }
        
        return {
            "content": json.dumps(export_data, indent=2),
            "content_type": "application/json",
            "filename": f"question_results_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        }
    
    async def _export_results_csv(
        self, 
        job: Job, 
        results: List[QuestionResult]
    ) -> Dict[str, Any]:
        """
        Export results in CSV format.
        
        Args:
            job: Job containing results
            results: List of question results
            
        Returns:
            CSV export data
        """
        # Create CSV content
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = [
            "question_id",
            "question_text",
            "response",
            "confidence_score",
            "processing_time",
            "success",
            "fragments_found",
            "error"
        ]
        writer.writerow(headers)
        
        # Write data rows
        for result in results:
            row = [
                result.question_id,
                result.question_text,
                result.response,
                result.confidence_score,
                result.processing_time,
                result.success,
                "; ".join(result.fragments_found),
                result.error or ""
            ]
            writer.writerow(row)
        
        csv_content = output.getvalue()
        output.close()
        
        return {
            "content": csv_content,
            "content_type": "text/csv",
            "filename": f"question_results_{job.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    
    async def get_question_job_status(self, job_id: str) -> Optional[Job]:
        """
        Get status of a question processing job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job details or None if not found
        """
        try:
            job = await self.job_repository.get_by_id(job_id)
            if job and job.type == JobType.QUESTION_PROCESSING:
                return job
            return None
            
        except Exception as e:
            logger.error(f"Error getting question job status for {job_id}: {e}")
            return None
    
    async def get_question_results(self, job_id: str) -> Optional[QuestionResults]:
        """
        Get question results for a completed job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Question results or None if not found/not completed
        """
        try:
            job = await self.job_repository.get_job_with_results(job_id)
            if not job or job.type != JobType.QUESTION_PROCESSING:
                return None
            
            if not job.is_completed or not job.result:
                return None
            
            # Extract results from job
            job_result = job.result
            results_data = job_result.get("results", [])
            
            # Convert to QuestionResult objects
            results = [QuestionResult(**result_data) for result_data in results_data]
            
            # Create QuestionResults object
            question_results = QuestionResults(
                job_id=job.id,
                workspace_id=job.workspace_id or "",
                results=results,
                summary=job_result.get("summary", {}),
                total_questions=job_result.get("total_questions", len(results)),
                successful_questions=job_result.get("successful_questions", 0),
                failed_questions=job_result.get("failed_questions", 0),
                total_processing_time=job_result.get("total_processing_time", 0.0),
                average_confidence=job_result.get("average_confidence", 0.0)
            )
            
            return question_results
            
        except Exception as e:
            logger.error(f"Error getting question results for job {job_id}: {e}")
            return None
    
    async def export_results(self, job_id: str, format: ExportFormat) -> str:
        """
        Export question results in specified format.
        
        Args:
            job_id: Job ID to export results for
            format: Export format (JSON or CSV)
            
        Returns:
            Exported data as string
            
        Raises:
            ExportError: If export fails
        """
        try:
            logger.debug(f"Exporting results for job {job_id} in {format} format")
            
            # Get job results
            job = await self.job_repository.get_by_id(job_id)
            if not job or job.type != JobType.QUESTION_PROCESSING:
                raise ExportError(f"Question processing job {job_id} not found")
            
            if not job.result:
                raise ExportError(f"No results available for job {job_id}")
            
            results_data = job.result.get("results", [])
            if not results_data:
                raise ExportError(f"No question results found for job {job_id}")
            
            if format == ExportFormat.JSON:
                return json.dumps(job.result, indent=2, default=str)
            
            elif format == ExportFormat.CSV:
                # Create CSV content
                output = StringIO()
                writer = csv.writer(output)
                
                # Write header
                headers = [
                    "question_id",
                    "question_text", 
                    "response",
                    "confidence_score",
                    "processing_time",
                    "success",
                    "error",
                    "fragments_found",
                    "llm_model"
                ]
                writer.writerow(headers)
                
                # Write data rows
                for result in results_data:
                    fragments_str = "; ".join(result.get("fragments_found", []))
                    llm_model = result.get("metadata", {}).get("llm_model", "")
                    
                    row = [
                        result.get("question_id", ""),
                        result.get("question_text", ""),
                        result.get("response", ""),
                        result.get("confidence_score", 0.0),
                        result.get("processing_time", 0.0),
                        result.get("success", False),
                        result.get("error", ""),
                        fragments_str,
                        llm_model
                    ]
                    writer.writerow(row)
                
                return output.getvalue()
            
            else:
                raise ExportError(f"Unsupported export format: {format}")
                
        except Exception as e:
            logger.error(f"Error exporting results for job {job_id}: {e}")
            if isinstance(e, ExportError):
                raise
            raise ExportError(f"Export failed: {e}")

    async def cancel_question_job(self, job_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancel a question processing job.
        
        Args:
            job_id: Job ID to cancel
            reason: Optional cancellation reason
            
        Returns:
            True if cancellation successful
        """
        try:
            job = await self.job_repository.get_by_id(job_id)
            if not job or job.type != JobType.QUESTION_PROCESSING:
                return False
            
            await self.job_repository.cancel_job(job_id, reason)
            logger.info(f"Cancelled question processing job {job_id}: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Error cancelling question job {job_id}: {e}")
            return False


# Factory function for dependency injection
def create_question_service(
    settings: Settings,
    job_repository: JobRepository,
    anythingllm_client: AnythingLLMClient,
) -> QuestionService:
    """
    Create QuestionService instance with dependencies.
    
    Args:
        settings: Application settings
        job_repository: Job repository
        anythingllm_client: AnythingLLM client
        
    Returns:
        Configured QuestionService instance
    """
    return QuestionService(
        settings=settings,
        job_repository=job_repository,
        anythingllm_client=anythingllm_client,
    )