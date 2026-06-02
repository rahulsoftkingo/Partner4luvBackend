import stripe
import os
from dotenv import load_dotenv

# Load environment variables from .env in the same directory
base_dir = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(base_dir, '.env')
load_dotenv(dotenv_path)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

def create_checkout_session(user_id: int, price_id: str, success_url: str, cancel_url: str, mode: str = "payment", extra_metadata: dict = None, customer_id: str = None):
    """
    mode can be "payment" (for one-time coin packages) or "subscription"
    """
    try:
        metadata = {
            "user_id": user_id,
            "mode": mode
        }
        if extra_metadata:
            metadata.update(extra_metadata)

        session_data = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'mode': mode,
            'success_url': success_url,
            'cancel_url': cancel_url,
            'client_reference_id': str(user_id),
            'metadata': metadata
        }

        if customer_id:
            session_data['customer'] = customer_id

        session = stripe.checkout.Session.create(**session_data)
        return session.url
    except Exception as e:
        print(f"STRIPE ERROR: {str(e)}")
        return None

def verify_webhook_signature(payload, sig_header):
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event
    except Exception as e:
        print(f"WEBHOOK ERROR: {str(e)}")
        return None
