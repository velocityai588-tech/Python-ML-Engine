import uuid
from datetime import datetime, timedelta
from app.db.supabase import supabase

# CONFIGURATION - Replace with a real Org ID from your DB
ORG_ID = "YOUR_ORGANIZATION_UUID_HERE"

def generate_mock_data():
    print(f"Generating mock data for Org: {ORG_ID}...")

    # 1. Fetch some real users from your DB to attach data to
    users_response = supabase.table("users").select("id, email").eq("organization_id", ORG_ID).limit(5).execute()
    users = users_response.data

    if not users:
        print("❌ No users found in this organization. Add users to 'public.users' first.")
        return

    # 2. Add Mock Jira Issues (Proven History)
    # We want the AI to see that these people have actually DONE the work.
    mock_issues = []
    for user in users:
        mock_issues.append({
            "org_id": ORG_ID,
            "cloud_id": "mock-cloud-123",
            "project_key": "VEL",
            "issue_key": f"VEL-{uuid.uuid4().hex[:3].upper()}",
            "summary": f"Developed {user['email'].split('@')[0]}'s feature module",
            "status": "Done",
            "assignee_email": user['email'],
            "issue_type": "Task",
            "story_points": 5,
            "updated_at": datetime.now().isoformat()
        })
    
    supabase.table("jira_issues").insert(mock_issues).execute()
    print(f"✅ Created {len(mock_issues)} proven Jira issues.")

    # 3. Add a Leave Request (The "Conflict" Test)
    # We'll put the first user on leave so the AI avoids assigning them.
    target_user = users[0]
    leave_data = {
        "org_id": ORG_ID,
        "user_id": target_user['id'],
        "name": "Annual Vacation",
        "start_date": "2026-03-05", # Overlaps with our test window
        "end_date": "2026-03-15",
        "status": "approved"
    }
    
    supabase.table("leave_requests").insert(leave_data).execute()
    print(f"✅ Created leave conflict for {target_user['email']}.")

if __name__ == "__main__":
    generate_mock_data()