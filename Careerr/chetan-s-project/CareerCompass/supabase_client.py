"""
CareerCompass - Supabase Database Integration Client
Handles real-time synchronization of student registrations, profile updates,
assessment submissions, and roadmap progress to your Supabase PostgreSQL cloud database.
"""

import os
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Supabase Credentials (Loaded from environment variables with safe defaults)
SUPABASE_PROJECT_ID = os.environ.get("SUPABASE_PROJECT_ID", "cipybtfndzbrepbtpcxd")
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL",
    f"https://{SUPABASE_PROJECT_ID}.supabase.co" if SUPABASE_PROJECT_ID else ""
).rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_gpUg0fZ2yt7QUGdbX3DLDA__wmxm5AY")


def is_supabase_configured() -> bool:
    """Checks whether valid Supabase configuration is present."""
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _supabase_request(endpoint: str, data: dict = None, method: str = "GET", extra_headers: dict = None):
    """
    Executes an HTTP request to the Supabase PostgREST API using standard urllib.
    Returns (success: bool, response_data: dict|list|str, error_message: str|None).
    """
    if not is_supabase_configured():
        return False, None, "Supabase credentials not configured."

    url = f"{SUPABASE_URL}/rest/v1/{endpoint.lstrip('/')}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    if extra_headers:
        headers.update(extra_headers)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            resp_body = response.read().decode("utf-8")
            parsed = json.loads(resp_body) if resp_body else None
            return True, parsed, None
    except urllib.error.HTTPError as e:
        raw_err = e.read().decode("utf-8")
        try:
            err_json = json.loads(raw_err)
            msg = err_json.get("message", raw_err)
            hint = err_json.get("hint")
            code = err_json.get("code")
            detail = f"[{code}] {msg}" + (f" (Hint: {hint})" if hint else "")
        except Exception:
            detail = raw_err
        logger.warning("Supabase %s %s failed (HTTP %s): %s", method, endpoint, e.code, detail)
        return False, None, detail
    except Exception as e:
        logger.warning("Supabase %s %s network error: %s", method, endpoint, str(e))
        return False, None, str(e)


def sync_user_to_supabase(user_dict: dict) -> tuple[bool, str | None]:
    """
    Pushes a new registered student to the Supabase 'users' table.
    Gracefully adapts to columns currently defined in the Supabase schema.
    """
    if not is_supabase_configured():
        return False, "Supabase not configured."

    # Full payload matching CareerCompass schema
    full_payload = {
        "full_name": user_dict.get("full_name"),
        "email": user_dict.get("email"),
        "college_name": user_dict.get("college_name"),
        "branch": user_dict.get("branch"),
        "academic_year": user_dict.get("academic_year"),
        "created_at": user_dict.get("created_at"),
        "role": user_dict.get("role", "user")
    }

    # Attempt insert with full payload
    success, res, err = _supabase_request("users", data=full_payload, method="POST")
    if success:
        logger.info("Successfully synced student %s to Supabase users table.", user_dict.get("email"))
        return True, None

    # If failure was due to missing columns in Supabase schema (PGRST204), fallback to core columns
    if err and "PGRST204" in err:
        fallback_payload = {
            "full_name": user_dict.get("full_name"),
            "email": user_dict.get("email"),
            "college_name": user_dict.get("college_name"),
            "created_at": user_dict.get("created_at")
        }
        success2, res2, err2 = _supabase_request("users", data=fallback_payload, method="POST")
        if success2:
            logger.info("Synced student %s to Supabase users using fallback columns.", user_dict.get("email"))
            return True, None
        return False, err2

    return False, err


def sync_profile_to_supabase(profile_dict: dict) -> tuple[bool, str | None]:
    """
    Upserts a student's profile into the Supabase 'profiles' table.
    """
    if not is_supabase_configured():
        return False, "Supabase not configured."

    payload = {
        "user_id": profile_dict.get("user_id"),
        "technical_skills": profile_dict.get("technical_skills"),
        "interests": profile_dict.get("interests"),
        "preferred_career": profile_dict.get("preferred_career"),
        "updated_at": profile_dict.get("updated_at")
    }
    headers = {"Prefer": "resolution=merge-duplicates,return=representation"}
    success, res, err = _supabase_request("profiles", data=payload, method="POST", extra_headers=headers)
    return success, err


def sync_assessment_to_supabase(assessment_dict: dict) -> tuple[bool, str | None]:
    """
    Inserts a completed diagnostic assessment record into Supabase 'assessments' table.
    """
    if not is_supabase_configured():
        return False, "Supabase not configured."

    payload = {
        "user_id": assessment_dict.get("user_id"),
        "taken_at": assessment_dict.get("taken_at"),
        "recommended_career": assessment_dict.get("recommended_career"),
        "alternative_career": assessment_dict.get("alternative_career"),
        "score_total": assessment_dict.get("score_total"),
        "percentage_total": assessment_dict.get("percentage_total"),
        "domain_scores_json": assessment_dict.get("domain_scores_json"),
        "explanation": assessment_dict.get("explanation"),
        "question_ids_json": assessment_dict.get("question_ids_json")
    }
    success, res, err = _supabase_request("assessments", data=payload, method="POST")
    return success, err


def sync_roadmap_task_to_supabase(task_dict: dict) -> tuple[bool, str | None]:
    """
    Upserts a roadmap task completion state into Supabase 'roadmap_progress' table.
    """
    if not is_supabase_configured():
        return False, "Supabase not configured."

    payload = {
        "user_id": task_dict.get("user_id"),
        "career_domain": task_dict.get("career_domain"),
        "task_id": task_dict.get("task_id"),
        "completed": task_dict.get("completed"),
        "updated_at": task_dict.get("updated_at")
    }
    headers = {"Prefer": "resolution=merge-duplicates,return=representation"}
    success, res, err = _supabase_request("roadmap_progress?on_conflict=user_id,career_domain,task_id", data=payload, method="POST", extra_headers=headers)
    return success, err


def test_supabase_connection() -> dict:
    """
    Diagnoses connectivity and permission status for all CareerCompass tables in Supabase.
    """
    if not is_supabase_configured():
        return {"status": "error", "message": "Supabase credentials not configured."}

    results = {}
    for table in ["users", "profiles", "assessments", "roadmap_progress"]:
        success, data, err = _supabase_request(f"{table}?select=*&limit=1", method="GET")
        results[table] = {
            "exists": success,
            "error": err if not success else None
        }

    return {
        "status": "connected" if results["users"]["exists"] else "partial",
        "project_id": SUPABASE_PROJECT_ID,
        "url": SUPABASE_URL,
        "tables": results
    }
