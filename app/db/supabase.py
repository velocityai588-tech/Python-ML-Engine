import os
from supabase import create_client, Client
from app.core.config import settings

# Create the client instance
url: str = settings.SUPABASE_URL
key: str = settings.SUPABASE_KEY

# This variable name MUST be 'supabase' to match your import statement
supabase: Client = create_client(url, key)