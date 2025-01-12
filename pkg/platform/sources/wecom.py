from __future__ import annotations
import typing
import asyncio
import traceback
import time
import datetime

import aiocqhttp
import aiohttp
from libs.wecom_api.api import WecomClient
from pkg.platform.adapter import MessageSourceAdapter
from pkg.platform.types import events as platform_events, message as platform_message
from libs.wecom_api.wecomevent import WecomEvent
from pkg.core import app

from .. import adapter
from ...pipeline.longtext.strategies import forward
from ...core import app
from ..types import message as platform_message
from ..types import events as platform_events
from ..types import entities as platform_entities
from ...command.errors import ParamNotEnoughError


class WecomMessageConverter(adapter.MessageConverter):
    @staticmethod
    async def yiri2target(message_chain:platform_message.MessageChain):
        content=''
        for msg in message_chain:
            if type(msg) is platform_message.Plain:
                content+=msg.text
        
        return content
                

    @staticmethod
    async def target2yiri(message:str,message_id:int = -1):
        yiri_msg_list = []
        yiri_msg_list.append(
            platform_message.Source(id = message_id,time = datetime.datetime.now())
        )

        yiri_msg_list.append(platform_message.Plain(text=message))
        chain = platform_message.MessageChain(yiri_msg_list)

        return chain




class WecomEventConverter:
    @staticmethod
    async def yiri2target(event:platform_events.Event,bot_account_id:int) -> WecomEvent:
            content = await WecomMessageConverter.yiri2target(event.message_chain)

            if type(event) is platform_events.GroupMessage:
                    pass
        
            if type(event) is platform_events.FriendMessage:
                payload = {
                    "MsgType": "text",
                    "Content": content,
                    "FromUserName": event.sender.id,
                    "ToUserName":  bot_account_id,
                    "CreateTime": int(datetime.datetime.now().timestamp()),
                    "AgentID": event.sender.nickname
                }
            wecom_event = WecomEvent.from_payload(payload=payload)
            if not wecom_event:
                raise ValueError("无法从 message_data 构造 WecomEvent 对象")
            return wecom_event
    
    @staticmethod
    async def target2yiri(event: WecomEvent):
        """
        将 WecomEvent 转换为平台的 FriendMessage 对象。

        Args:
            event (WecomEvent): 企业微信事件。

        Returns:
            platform_events.FriendMessage: 转换后的 FriendMessage 对象。
        """
        # 转换消息链
        yiri_chain = await WecomMessageConverter.target2yiri(
            event.message, event.message_id
        )

        # 判断消息类型并进行转换
        # if event.message_type == "private": 默认消息都是从好友发出

        friend = platform_entities.Friend(
            id=event.user_id,  
            nickname=str(event.agent_id),   
            remark="",         
        )
        
        return platform_events.FriendMessage(
                sender=friend,
                message_chain=yiri_chain,
                time=event.timestamp
            )

        

@adapter.adapter_class("wecom")
class WecomeAdapter(adapter.MessageSourceAdapter):

    bot:WecomClient    
    ap:app.Application
    bot_account_id:str
    message_converter:WecomMessageConverter = WecomMessageConverter()
    event_converter:WecomEventConverter = WecomEventConverter()
    config:dict
    ap:app.Application

    def __init__(self, config: dict, ap:app.Application):
        self.config = config
        #这里需要对config里的内容换成企业微信的config。是config:corpid,token......
        self.ap = ap
        
        required_keys = ["corpid","secret","token","EncodingAESKey","contacts_secret"]
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise ParamNotEnoughError("企业微信缺少相关配置项，请查看文档或联系管理员")

        self.bot = WecomClient(
            corpid=config['corpid'],
            secret=config['secret'],
            token=config['token'],
            EncodingAESKey=config['EncodingAESKey'],
            contacts_secret=config['contacts_secret']
        )
        
    async def reply_message(self,message_source:platform_events.MessageEvent,message:platform_message.MessageChain,
            quote_origin:bool=False,
    ):
        Wecom_event = await WecomEventConverter.yiri2target(message_source,self.bot_account_id)
        Wecom_msg = await WecomMessageConverter.yiri2target(message)
        # message_converter传回一个消息str

        user_id = Wecom_event.user_id
        agent_id = Wecom_event.agent_id
        return await self.bot.send_private_msg(user_id=user_id,agent_id=agent_id,content=Wecom_msg)

    async def send_message(self, target_type: str, target_id: str, message: platform_message.MessageChain):
        pass



    def register_listener(
            self,
            event_type:typing.Type[platform_events.Event],
            callback:typing.Callable[[platform_events.Event,adapter.MessageSourceAdapter],None],

    ):
        async def on_message(event:WecomEvent):
            self.bot_account_id = event.receiver_id
            try:
                return await callback(await self.event_converter.target2yiri(event),self)
            except:
                traceback.print_exc()
        if event_type == platform_events.FriendMessage:
            self.bot.on_message("text")(on_message)
        elif event_type == platform_events.GroupMessage:
            pass
    
    async def run_async(self):
        async def shutdown_trigger_placeholder():
            while True:
                await asyncio.sleep(1)

        await self.bot.run_task(host=self.config['host'],port=self.config['port'],shutdown_trigger=shutdown_trigger_placeholder)

    async def kill(self) -> bool:
        return False
    
    async def unregister_listener(self, event_type: type, callback: typing.Callable[[platform_events.Event, MessageSourceAdapter], None]):
        return super().unregister_listener(event_type, callback)

 












