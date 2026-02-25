import aiohttp
from typing import List, Tuple, Dict, Any, Literal, Union, get_args

# Old way (synchronous)
#response = wrapper.send_template(phone_number, template_name, params)

# New way (asynchronous)
#response = await wrapper.send_template(phone_number, template_name, params)

#Make sure to call these methods from within async functions or use asyncio.run() for the top-level call.

Key = Literal["header", "body"]
# The list(tuple) is used for positional parameters, while the dict allows for named parameters. 
# Both are accepted for flexibility.
NamedValue = List[Dict[Literal["parameter_name", "parameter_value"], str]]
PositionalValue = Union[List[str], Tuple[str]]
# The string is only accepted for the header component to allow for document links in the template.
Value = Union[str, NamedValue, PositionalValue]
Params = Dict[Key, Value]

class WhatsAppWrapper:
    """
    A wrapper for the WhatsApp Cloud API to send template messages.

    The footer and button components of a template message do not have parameters in a template.

    Because of this, the only way to send a document is to include it in the header of a template message.
    So, if we receive a string as the header value, we assume it is a link to the document.
    """
    def __init__(self, bearer_token: str, phone_number_id: str):
        self.bearer_token = bearer_token
        self.phone_number_id = phone_number_id
        self.base_url = f"https://graph.facebook.com/v23.0/{phone_number_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json",
        }


    async def _send_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message using the WhatsApp Cloud API."""
        async with aiohttp.ClientSession() as session:
            async with session.post(self.base_url, json=payload, headers=self.headers) as response:
                return await response.json()


    def header(self, hdr: Value) -> Dict[str, Any]:
        if isinstance(hdr, str):
            return {"type": "header", "parameters": [
                {
                    "type": "document", 
                    "document": 
                    {
                        # If the document is already uploaded to Facebook servers, use the document ID instead of the link.
                        # "id": document_id
                        "link": hdr,
                        # "filename": "document.pdf"  # Optional, but can be included for better user experience.
                    }
                }
            ]}
        else:
            hdr_params = self.handle_params(hdr)
            return {"type": "header", "parameters": hdr_params}


    def handle_params(self, params: Value) -> List[Dict[str, Any]]:
        component_params = []
        for v in params:
            if isinstance(v, str):
                """
                https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview#:~:
                text=Example%20template%20creation%20payload%20with%20positional%20parameter%3A
                """
                component_params.append({"type": "text", "text": v})
            elif isinstance(v, dict):
                """
                https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/overview#:~:
                text=Example%20template%20send%20payload%20of%20template%20that%20uses%20named%20parameters%3A
                """
                component_params.append(
                    {
                        "type": "text", 
                        "parameter_name": v["parameter_name"], 
                        "text": v["parameter_value"]
                    })
            else:
                raise ValueError("body parameter must be str or list")
        return component_params
    

    def body(self, body: Value) -> Dict[str, Any]:
        body_params = self.handle_params(body)
        return {"type": "body", "parameters": body_params}


    async def send_template(self, recipient_number: str, template_name: str, parameters: Params) -> Dict[str, Any]:
        """
        Send a template message.
        
        Args:
            recipient_number: Phone number in E.164 format
            template_name: Name of the template
            parameters: Dictionary of template parameters. Allowed keys: "header", "body".
                    Values should follow WhatsApp component parameter shapes; simple strings or lists of strings
                    for text parameters are accepted and will be converted.
        """
        allowed = set(get_args(Key))
        invalid = set(parameters.keys()) - allowed
        if invalid:
            raise ValueError(f"Invalid template component keys: {', '.join(invalid)}. Allowed: {', '.join(allowed)}")

        components = []

        # Header
        if "header" in parameters:
            components.append(self.header(parameters["header"]))

        # Body
        if "body" in parameters:
            components.append(self.body(parameters["body"]))

        # Footer and buttons are fixed in a template.

        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_number,
            "recipient_type": "individual",
            "type": "template",
            # The Id of the message being replied to.
            #"context": {"message_id": message_id},
            "template": {
                "name": template_name,
                "language": {"code": "en_US"},
                "components": components,
            },
        }

        return await self._send_message(payload)

