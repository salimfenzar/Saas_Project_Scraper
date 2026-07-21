from __future__ import annotations

from supabase import Client, create_client

from app.config import Settings



def create_supabase_client(settings: Settings) -> Client:
    settings.validate_runtime()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
