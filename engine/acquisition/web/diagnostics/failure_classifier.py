"""
Failure classifier mapping HTTP codes, document signals, and exceptions to explicit extraction states.
"""
from typing import Optional, Tuple
from engine.acquisition.web.models.extraction_result import ExtractionState


class FailureClassifier:
    """
    Translates HTTP status codes, security barriers, and content deficiencies into precise failure states.
    """

    def classify_http_error(self, status_code: int, response_text: str = "") -> Tuple[ExtractionState, str]:
        lower_body = response_text.lower()[:2048]

        # 401 Unauthorized
        if status_code == 401:
            return ExtractionState.AUTHENTICATION_REQUIRED, "HTTP 401: Authentication is required to view this chapter."

        # 403 Forbidden
        if status_code == 403:
            if "cloudflare" in lower_body or "turnstile" in lower_body or "cf-mitigated" in lower_body:
                return ExtractionState.CHALLENGE_PRESENT, "Cloudflare or bot verification challenge present on server."
            return ExtractionState.ACCESS_RESTRICTED, "HTTP 403: Access to this chapter resource is forbidden or restricted."

        # 429 Too Many Requests
        if status_code == 429:
            return ExtractionState.RATE_LIMITED, "HTTP 429: Rate limit exceeded. Backoff and respect host rate limits."

        # 404 Not Found
        if status_code == 404:
            return ExtractionState.NOT_A_CHAPTER, "HTTP 404: The specified URL or chapter could not be found."

        # 5xx Server Error
        if 500 <= status_code < 600:
            return ExtractionState.FAILED_NETWORK, f"HTTP {status_code}: Upstream server encountered a transient error."

        return ExtractionState.FAILED_NETWORK, f"Unexpected HTTP status {status_code}"

    def classify_content_anomaly(
        self,
        has_login_form: bool = False,
        has_challenge_text: bool = False,
        page_type: str = "UNKNOWN_PAGE",
        candidates_found: int = 0,
        completeness_score: float = 0.0,
    ) -> Tuple[ExtractionState, str]:
        if has_login_form:
            return ExtractionState.AUTHENTICATION_REQUIRED, "Page presents a mandatory login prompt."

        if has_challenge_text:
            return ExtractionState.CHALLENGE_PRESENT, "Verification challenge / Captcha page detected."

        if page_type == "NOT_CONTENT":
            return ExtractionState.NOT_A_CHAPTER, "Input document does not represent a comic/manga chapter."

        if page_type == "SERIES_PAGE":
            return ExtractionState.NOT_A_CHAPTER, "URL is a series index / table of contents, not an individual chapter."

        if candidates_found == 0:
            return ExtractionState.NO_CONTENT_IMAGES, "No content images discovered across extraction strategies."

        if completeness_score < 0.40:
            return ExtractionState.UNSUPPORTED_READER, f"Reader structure unsupported or incomplete (completeness={completeness_score:.2f})."

        return ExtractionState.NEEDS_REVIEW, f"Extraction produced low-confidence results ({completeness_score:.2f}) requiring user confirmation."
