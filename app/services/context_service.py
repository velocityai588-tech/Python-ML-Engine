from app.db.supabase import supabase

async def get_employee_history(organization_id: str, user_emails: list):
    # Fetch recent completed tasks for these specific users
    response = supabase.table("jira_issues") \
        .select("assignee_email, summary, time_spent_seconds, status") \
        .filter("organization_id", "eq", organization_id) \
        .filter("assignee_email", "in", user_emails) \
        .filter("status", "eq", "Done") \
        .limit(100) \
        .execute()

    # Grouping history by email
    history_map = {}
    for issue in response.data:
        email = issue['assignee_email']
        if email not in history_map:
            history_map[email] = []
        # Keep it short to save tokens
        history_map[email].append(issue['summary'])
    
    return history_map