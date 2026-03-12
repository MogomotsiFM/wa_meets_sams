import os
import copy
import logging
import aiohttp
import socket
import mimetypes

from pathlib import Path
from aiohttp import web

from typing import List, Tuple, Dict, Any, Literal, Union, get_args

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger()


Key = Literal["header", "body"]
# The list(tuple) is used for positional parameters, while the dict allows for named parameters. 
# Both are accepted for flexibility.
NamedValue = List[Dict[Literal["parameter_name", "parameter_value"], str]]
PositionalValue = Union[List[str], Tuple[str]]
# The string is only accepted for the header component to allow for document links in the template.
Value = Union[str, NamedValue, PositionalValue]
Params = Dict[Key, Value]

Method = Literal["PUT", "POST", "GET"]
HeaderType = Literal["text", "image", "document"]

class WhatsAppWrapper:
    """
    A wrapper for the WhatsApp Cloud API to send template messages.

    The footer and button components of a template message do not have parameters in a template.
    """
    def __init__(self, bearer_token: str, phone_number_id: str):
        self.bearer_token = bearer_token
        self.phone_number_id = phone_number_id
        self.base_url = f'https://graph.facebook.com/v23.0/{phone_number_id}/'
        self.headers = {
            'Authorization': f'Bearer {bearer_token}',
            'Content-Type': 'application/json',
        }
        self.OPT_IN_MESSAGE_TEMPLATE_NAME = os.getenv("OPT_IN_MESSAGE_TEMPLATE_NAME")
        self.PROGRESS_REPORT_TEMPLATE_NAME = os.getenv("PROGRESS_REPORT_TEMPLATE_NAME")
        self.PROXY_URL = os.getenv("PROXY_URL")

        # create a single session to reuse across multiple calls
        trace_config = aiohttp.TraceConfig()
        trace_config.on_request_start.append(self.on_request_start)
        trace_config._on_request_chunk_sent(self.on_chunk_sent)
        self.timeout = aiohttp.ClientTimeout(total=60, sock_read=30)
        self.session = aiohttp.ClientSession(timeout=self.timeout)#, trace_configs=[trace_config])
        #self.session = aiohttp.ClientSession(timeout=self.timeout, middlewares=[self.middleware])


    async def send_opt_in_message(self, recipient_number, image_id, date, weekday, time):
        template_name = self.OPT_IN_MESSAGE_TEMPLATE_NAME
        params = {
            "header":{
                "type": "image",
                "upload_id": image_id
            },
            "body": [
                {
                    "parameter_name": "date",
                    "parameter_value": date   
                },
                {
                    "parameter_name": "weekday",
                    "parameter_value": weekday
                },
                {
                    "parameter_name": "time",
                    "parameter_value": time
                }
            ]
        }
        logger.info("(WhatsappWrapper)   Sending opt-in template message.")
        response = await self.send_template(recipient_number, template_name, params)
        return response


    async def send_message_read(self, msg_id):
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": msg_id
        }
        response = await self._send_message("PUT", "messages", payload=payload)
        logger.info("(WhatsappWrapper)  Sent read receipt.")
        return response


    async def upload(self, file_path: str, filename: str):
        content_type, _ = mimetypes.guess_type(file_path)
        logger.info(f"(WhatsappWrapper)  content type: {content_type}")
        if content_type is None:
            raise ValueError(f"File {file_path} has an unknown content type.")

        data = aiohttp.FormData()
        data.add_field("messaging_product", "whatsapp")
        with open(file_path, "rb") as f:
            ext = file_path.split(".")[-1]
            logger.debug(f"(WhatsappWrapper)  File extension: {ext}")
            data.add_field(
                "file",
                f,
                filename=f"{filename}.{ext}",
                content_type=content_type
            )
            headers = copy.deepcopy(self.headers)
            # The aiohttp package will set the correct content type.
            # We are removing this one just in case we overwrite that value.
            # We have cached the original header just above so we can reset it. 
            self.headers.pop("Content-Type")
            response = await self._send_message(method="POST", route="media", data=data)
            self.headers = headers
            return response


    async def send_progress_report(self, recipient_number, report_id):
        template_name = self.PROGRESS_REPORT_TEMPLATE_NAME
        params = {
            "header":{
                "type": "document",
                "upload_id": report_id
            },
        }
        response = await self.send_template(recipient_number, template_name, params)
        return response


    async def _send_message(self, method: Method, route: Literal["messages", "media"], payload: Dict[str, Any]|None=None, data=None) -> Dict[str, Any]:
        """Send a message using the WhatsApp Cloud API.

        The :attr:`session` is created in ``__init__`` and reused; this helper simply
        dispatches the correct verb.
        """
        logger.info(f"(WhatsappWrapper)  Sending {method} message.")

        endpoint = self.base_url + route
        try:
            if method == "POST":
                async with self.session.post(endpoint, json=payload, data=data, headers=self.headers) as response:
                    return await response.json()
            elif method == "PUT":
                async with self.session.put(endpoint, json=payload, data=data, headers=self.headers) as response:
                    return await response.json()
            else:
                error_msg = f"HTTP method f{method} was not implemented."
                logger.error(error_msg)
                return  {
                    "status_code": 501,
                    "status": "Failure", 
                    "message": f"HTTP method f{method} was not implemented"
                }
        except Exception:  # keep broad catch for timeouts/connection errors
            logger.info("(WhatsappWrapper)  Sending messages to Whatsapp timed out.")
            return  {
                    "status_code": 501,
                    "status": "Failure", 
                    "message": "(WhatsappWrapper)  Sending messages to Whatsapp timed out."
                }


    async def on_request_start(self, session: aiohttp.ClientSession, trace_config_ctx, chunk):
        logger.info("(aiohttp) Starting request")
        logger.info(f"(aiohttp) Request: {chunk}")

    async def on_chunk_sent(self, session: aiohttp.ClientSession, trace_config_ctx, chunk):
        logger.info(f"(aiohttp) Sent chunk: {chunk}")

    async def middleware(self, req: aiohttp.ClientRequest, handler):
        logger.debug(f"(aiohttp) Prepared headers: {vars(req.headers)}")
        logger.debug(f"(aiohttp) Request body: {vars(req.body)}")
        response = await handler(req)
        return response


    def header(self, hdr: Value) -> Dict[str, Any]:
        if isinstance(hdr, dict): # If type is image or document
            return {
                "type": "header", 
                "parameters": [
                    {
                        "type": hdr["type"], 
                        f'{hdr["type"]}': 
                        {
                            # If the document is already uploaded to Facebook servers, use the document ID instead of the link.
                            "id": hdr["upload_id"]
                            #"link": hdr["upload_link"],
                            # "filename": "document.pdf"  # Optional, but can be included for better user experience.
                        }
                    }
                ]
            }
        else: # If type is text. Even then, there can only be one parameter.
            # That is, we have a list with only one item. A list with a single string
            # for positional parameters. And a list with a single dictionary for
            # named parameters.
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
                "language": {"code": "en"},
                "components": components,
            },
        }
        return await self._send_message("POST", "messages", payload=payload)


    async def close(self) -> None:
        """Shut down the underlying :class:`aiohttp.ClientSession`.

        Clients should call this when the wrapper is no longer needed, or use
        ``async with`` which calls it automatically.
        """
        if not self.session.closed:
            await self.session.close()


    async def __aenter__(self):
        return self


    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

