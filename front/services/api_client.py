import requests
import os
from typing import Optional, List

class APIClient:
    def __init__(self):
        # Get API base URL from environment variable or use default
        self.base_url = os.getenv('API_BASE_URL', 'http://localhost:8766')
        
    def _make_request(self, method, endpoint, token=None, **kwargs):
        """Make HTTP request to the API"""
        url = f"{self.base_url}{endpoint}"
        headers = {}
        if token:
            headers['Authorization'] = f"Bearer {token}"
            
        try:
            response = requests.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            raise
    
    # Auth methods
    def register(self, username: str, password: str):
        """Register a new user"""
        data = {"username": username, "password": password}
        return self._make_request("POST", "/auth/register", json=data)
    
    def login(self, username: str, password: str):
        """Login user and get token"""
        data = {"username": username, "password": password}
        return self._make_request("POST", "/auth/login", json=data)
    
    def list_users(self, token: str):
        """List all users"""
        return self._make_request("GET", "/users", params={"token": token})
    
    # Group methods
    def create_group(self, name: str, description: str, is_hierarchical: bool, 
                     token: str, members: Optional[List[int]] = None):
        """Create a new group"""
        data = {
            "name": name,
            "description": description,
            "is_hierarchical": is_hierarchical,
            "members": members or []
        }
        return self._make_request("POST", "/groups", json=data, params={"token": token})
    
    def list_user_groups(self, token: str):
        """List groups for current user"""
        return self._make_request("GET", "/groups", params={"token": token})
    
    def list_group_members(self, group_id: int, token: str):
        """List members of a group"""
        return self._make_request("GET", f"/groups/{group_id}/members", params={"token": token})
    
    def invite_user_to_group(self, group_id: int, invited_user_id: int, token: str):
        """Invite user to a group"""
        data = {"group_id": group_id, "invited_user_id": invited_user_id}
        return self._make_request("POST", "/groups/invite", json=data, params={"token": token})
    
    def get_pending_invitations(self, token: str):
        """Get pending group invitations"""
        return self._make_request("GET", "/groups/invitations", params={"token": token})
    
    def respond_to_group_invitation(self, invitation_id: int, response: str, token: str):
        """Respond to a group invitation"""
        data = {"invitation_id": invitation_id, "response": response}
        return self._make_request("POST", "/groups/invitations/respond", json=data, params={"token": token})
    
    def get_pending_invitations_count(self, token: str):
        """Get count of pending group invitations"""
        return self._make_request("GET", "/groups/invitations/count", params={"token": token})
    
    def update_group(self, group_id: int, name: Optional[str] = None, description: Optional[str] = None, token: str = ""):
        """Update group information (name and/or description)"""
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        return self._make_request("PUT", f"/groups/{group_id}", json=data, params={"token": token})
    
    def delete_group(self, group_id: int, token: str):
        """Delete a group completely"""
        return self._make_request("DELETE", f"/groups/{group_id}", params={"token": token})
    
    def remove_member(self, group_id: int, member_id: int, token: str):
        """Remove a member from a group"""
        return self._make_request("DELETE", f"/groups/{group_id}/members/{member_id}", params={"token": token})
    
    def get_group_info(self, group_id: int, token: str):
        """Get complete group information"""
        return self._make_request("GET", f"/groups/{group_id}/info", params={"token": token})

    # Event methods
    def create_event(self, title: str, description: str, start_time: str, end_time: str,
                     token: str, group_id: Optional[int] = None, is_group_event: bool = False,
                     participants_ids: Optional[List[int]] = None, is_hierarchical: bool = False):
        """Create a new event"""
        data = {
            "title": title,
            "description": description,
            "start_time": start_time,
            "end_time": end_time,
            "group_id": group_id,
            "is_group_event": is_group_event,
            "participants_ids": participants_ids or [],
            "is_hierarchical": is_hierarchical
        }
        return self._make_request("POST", "/events", json=data, params={"token": token})
    
    def get_user_events(self, token: str):
        """Get user events"""
        return self._make_request("GET", "/events", params={"token": token})
    
    def get_user_events_detailed(self, token: str, filter_type: str = "all"):
        """Get detailed user events"""
        return self._make_request("GET", "/events/detailed", params={"token": token, "filter_type": filter_type})
    
    def get_pending_event_invitations(self, token: str):
        """Get pending event invitations"""
        return self._make_request("GET", "/events/invitations", params={"token": token})
    
    def respond_to_event_invitation(self, event_id: int, accepted: bool, token: str):
        """Respond to an event invitation"""
        data = {"event_id": event_id, "accepted": accepted}
        return self._make_request("POST", "/events/invitations/respond", json=data, params={"token": token})
    
    def get_pending_event_invitations_count(self, token: str):
        """Get count of pending event invitations"""
        return self._make_request("GET", "/events/invitations/count", params={"token": token})
    
    def cancel_event(self, event_id: int, token: str):
        """Cancel an event (only for creators)"""
        return self._make_request("DELETE", f"/events/{event_id}", params={"token": token})
    
    def leave_event(self, event_id: int, token: str):
        """Leave an event (only for participants)"""
        return self._make_request("DELETE", f"/events/{event_id}/leave", params={"token": token})
    
    def get_event_details(self, event_id: int, token: str):
        """Get complete event details including participants"""
        return self._make_request("GET", f"/events/{event_id}/details", params={"token": token})
