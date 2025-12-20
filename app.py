"""Slack Bolt entrypoint for Evidently."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from blocks.home_tab import build_home_tab
from blocks.interactions import error_block, so_what_blocks
from blocks.modals import decision_room_modal, generate_test_modal
from config import settings
from services.ai_service import aio_service
from services.db_service import db_service
from services.drive_service import drive_service

app = AsyncApp(token=settings.slack_bot_token, signing_secret=settings.slack_signing_secret)


@app.event("app_home_opened")
async def update_home_tab(event: Dict[str, Any], client, ack, logger):
    await ack()
    user_id = event.get("user")
    project = await db_service.get_project(user_id) or await db_service.create_project("New Project", user_id)
    assumptions = await db_service.list_assumptions(project.get("id"))
    current_view = await db_service.get_current_view(user_id)
    try:
        view = await build_home_tab(project, assumptions, current_view)
        await client.views_publish(user_id=user_id, view=view)
    except Exception as exc:
        logger.error("Failed to publish home tab: %s", exc)
        await client.chat_postMessage(channel=user_id, blocks=[error_block()])


@app.event("app_mention")
async def handle_mention(event: Dict[str, Any], say, ack):
    await ack()
    text = event.get("text", "")
    files = event.get("files", [])
    attachments: List[Dict[str, Any]] = []
    for item in files:
        attachments.append({"type": item.get("filetype", "file"), "text": item.get("name", "")})
    summary = await aio_service.generate_summary(text, attachments)
    if "error" in summary:
        await say(blocks=[error_block(summary["error"])])
        return

    await say(**so_what_blocks(summary))


@app.command("/evidently-link-doc")
async def link_doc(ack, respond, command, logger):
    await ack()
    text = command.get("text", "").strip()
    user_id = command.get("user_id")
    project = await db_service.get_project(user_id) or await db_service.create_project("New Project", user_id)
    if not text:
        await respond("Please provide a Google Doc link or ID.", response_type="ephemeral")
        return

    async def _process():
        success = await drive_service.sync_document(project.get("id"), text)
        if success:
            await respond(f"Synced evidence from {text}", response_type="ephemeral")
        else:
            await respond("Unable to sync that document right now.", response_type="ephemeral")

    asyncio.create_task(_process())


@app.action("sync_documents")
async def handle_sync(body, ack, client, logger):
    await ack()
    user_id = body.get("user", {}).get("id")
    project = await db_service.get_project(user_id) or await db_service.create_project("New Project", user_id)
    doc_id = project.get("linked_doc") or ""
    if not doc_id:
        await client.chat_postMessage(channel=user_id, text="No document linked yet.")
        return
    success = await drive_service.sync_document(project.get("id"), doc_id)
    if success:
        assumptions = await db_service.list_assumptions(project.get("id"))
        current_view = await db_service.get_current_view(user_id)
        view = await build_home_tab(project, assumptions, current_view)
        await client.views_publish(user_id=user_id, view=view)
    else:
        await client.chat_postMessage(channel=user_id, blocks=[error_block()])


@app.action("view_experiments")
async def handle_view_experiments(ack, body, client):
    await ack()
    await client.chat_postMessage(
        channel=body.get("user", {}).get("id"),
        text="Experiment tracking coming soon.",
    )


@app.action("add_assumption")
async def handle_add_assumption(ack, body, client):
    await ack()
    await client.chat_postMessage(
        channel=body.get("user", {}).get("id"),
        text="Use /evidently-link-doc or mention Evidently to add assumptions automatically.",
    )


async def _handle_navigation(ack, body, client, target_workspace: str):
    await ack()
    user_id = body.get("user", {}).get("id")
    project = await db_service.get_project(user_id) or await db_service.create_project("New Project", user_id)
    assumptions = await db_service.list_assumptions(project.get("id"))
    await db_service.set_current_view(user_id, target_workspace)
    view = await build_home_tab(project, assumptions, target_workspace)
    await client.views_publish(user_id=user_id, view=view)


@app.action("nav_overview")
async def nav_overview(ack, body, client):
    await _handle_navigation(ack, body, client, "overview")


@app.action("nav_discovery")
async def nav_discovery(ack, body, client):
    await _handle_navigation(ack, body, client, "discovery")


@app.action("nav_roadmap")
async def nav_roadmap(ack, body, client):
    await _handle_navigation(ack, body, client, "roadmap")


@app.action("nav_experiments")
async def nav_experiments(ack, body, client):
    await _handle_navigation(ack, body, client, "experiments")


@app.action("nav_team")
async def nav_team(ack, body, client):
    await _handle_navigation(ack, body, client, "team")


@app.shortcut("generate_test")
async def open_generate_test_modal(ack, body, client):
    await ack()
    trigger_id = body.get("trigger_id")
    assumption_text = body.get("message", {}).get("text", "")
    modal = generate_test_modal(assumption_text)
    await client.views_open(trigger_id=trigger_id, view=modal)


@app.action("generate_test")
async def open_generate_test_action(ack, body, client):
    await ack()
    trigger_id = body.get("trigger_id")
    assumption_text = ""
    actions = body.get("actions", [])
    if actions:
        assumption_text = actions[0].get("value", "")
    modal = generate_test_modal(assumption_text)
    await client.views_open(trigger_id=trigger_id, view=modal)


@app.action("start_decision_session")
async def start_decision_session(ack, body, client):
    await ack()
    user_id = body.get("user", {}).get("id")
    project = await db_service.get_project(user_id) or await db_service.create_project("New Project", user_id)
    assumptions = await db_service.list_assumptions(project.get("id"))
    trigger_id = body.get("trigger_id")
    modal = decision_room_modal(assumptions)
    await client.views_open(trigger_id=trigger_id, view=modal)


async def start() -> None:
    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(start())
