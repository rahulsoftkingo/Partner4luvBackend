from datetime import datetime, timezone
from typing import Dict, Any, Optional
from db import db

class SubscriptionManager:
    """
    Handles subscription checks, plan updates, and grandfathering logic.
    """

    @staticmethod
    async def get_user_permissions(user_id: int) -> Dict[str, Any]:
        """
        Determines what a user can do based on their tier and grandfathering status.
        """
        user = await db.user.find_unique(
            where={"id": user_id},
            include={"payments": {"orderBy": {"createdAt": "desc"}, "take": 1}}
        )
        
        if not user:
            return {"tier": "Basic", "features": ["swipe_limited", "chat_limited"]}

        # 1. Basic check
        current_tier = user.tier or "Basic"
        
        # 2. Check for Grandfathering (Legacy Plans)
        # If the user has an active Stripe subscription that is older than the current plan update date,
        # we treat them as a "Legacy" user with preserved features.
        is_legacy = False
        if user.stripeSubscriptionId:
            # Here we would normally check the 'created' date from Stripe
            # For now, we check the user's tier and if it matches a 'deprecated' plan name.
            if current_tier in ["Platinum_Legacy", "Gold_v1"]:
                is_legacy = True

        # 3. Define feature sets
        feature_map = {
            "Basic": {
                "max_swipes_daily": 10,
                "see_who_likes_you": False,
                "unlimited_chat": False,
                "ai_insight_count": 0
            },
            "Gold": {
                "max_swipes_daily": 50,
                "see_who_likes_you": True,
                "unlimited_chat": True,
                "ai_insight_count": 5
            },
            "Platinum": {
                "max_swipes_daily": -1, # Unlimited
                "see_who_likes_you": True,
                "unlimited_chat": True,
                "ai_insight_count": 20
            }
        }

        # If legacy, we might grant them the 'Platinum' features even if they are on a lower tier now
        active_features = feature_map.get(current_tier, feature_map["Basic"])
        
        if is_legacy:
            active_features["legacy_status"] = "ACTIVE"
            # Ensure they don't lose 'Unlimited Swipes' if they were promised it before
            active_features["max_swipes_daily"] = -1

        return {
            "userId": user_id,
            "tier": current_tier,
            "isLegacy": is_legacy,
            "features": active_features
        }

    @staticmethod
    async def process_plan_update(old_plan_id: str, new_plan_id: str):
        """
        Logic to run when an admin changes a subscription plan in the dashboard.
        Instead of force-migrating, we mark users for grandfathering.
        """
        # This would be called from the Admin API
        pass

subscription_manager = SubscriptionManager()
