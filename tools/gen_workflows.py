import json
import sys
import uuid
from pathlib import Path

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

SYS01_ID = "SYS01ErrHandler0"
SYS02_ID = "SYS02NotifyTgm00"
ONB01_ID = "ONB01StripeKick0"


def nid(wf, name):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{wf}/{name}"))


def node(wf, name, ntype, version, pos, params, **extra):
    n = {
        "parameters": params,
        "id": nid(wf, name),
        "name": name,
        "type": ntype,
        "typeVersion": version,
        "position": pos,
    }
    n.update(extra)
    return n


def link(*names):
    """Linear chain connections."""
    conns = {}
    for a, b in zip(names, names[1:]):
        conns.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": 0})
    return conns


def to(name, index=0):
    return {"node": name, "type": "main", "index": 0}


def workflow(wid, name, nodes, connections, error_workflow=None):
    settings = {"executionOrder": "v1"}
    if error_workflow:
        settings["errorWorkflow"] = error_workflow
    return {
        "id": wid,
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": settings,
        "active": False,
        "pinData": {},
    }


def save(fname, wf):
    (OUT / fname).write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


RETRY = {"retryOnFail": True, "maxTries": 3, "waitBetweenTries": 5000}
CONTINUE = {"onError": "continueRegularOutput"}


def http(wf, name, pos, url, body, cred_type, **extra):
    return node(wf, name, "n8n-nodes-base.httpRequest", 4.2, pos, {
        "method": "POST",
        "url": url,
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": cred_type,
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": body,
        "options": {},
    }, **extra)


def code(wf, name, pos, js):
    return node(wf, name, "n8n-nodes-base.code", 2, pos, {"jsCode": js.strip() + "\n"})


def sheets(wf, name, pos, operation, matching):
    return node(wf, name, "n8n-nodes-base.googleSheets", 4.5, pos, {
        "operation": operation,
        "documentId": {"__rl": True, "mode": "id",
                       "value": "={{ $('Config').first().json.config.registry_sheet_id }}"},
        "sheetName": {"__rl": True, "mode": "name",
                      "value": "={{ $('Config').first().json.config.registry_tab }}"},
        "columns": {"mappingMode": "autoMapInputData", "value": {},
                    "matchingColumns": matching, "schema": []},
        "options": {},
    }, **RETRY)


# =====================================================================
# SYS-01 Global Error Handler
# =====================================================================
W = "SYS-01"
FORMAT_ERROR = r"""
// === CONFIG ===
// Self-contained on purpose: if SYS-02 is broken, errors must still reach Telegram.
const ERRORS_CHAT_ID = 'REPLACE_WITH_TELEGRAM_ERRORS_CHAT_ID';

const d = $input.first().json;
const wf = d.workflow || {};
const ex = d.execution || {};
const tr = d.trigger || {}; // set instead of `execution` when the trigger node itself failed
const err = ex.error || tr.error || {};

const lines = [
  '🚨 Workflow failed',
  `Workflow: ${wf.name || 'unknown'} (${wf.id || '-'})`,
  `Node: ${ex.lastNodeExecuted || err.node?.name || (tr.error ? 'trigger' : 'unknown')}`,
  `Error: ${err.message || 'no message'}`,
];
if (err.description) lines.push(`Details: ${err.description}`);
if (ex.url) lines.push(`Execution: ${ex.url}`);
lines.push(`Mode: ${ex.mode || tr.mode || '-'}`);
lines.push(`Time: ${$now.toISO()}`);

let text = lines.join('\n');
if (text.length > 4000) text = text.slice(0, 3990) + '…';

return [{ json: { chat_id: ERRORS_CHAT_ID, text } }];
"""

save("SYS-01_error-handler.json", workflow(SYS01_ID, "[SYS-01] Global Error Handler", [
    node(W, "Error Trigger", "n8n-nodes-base.errorTrigger", 1, [0, 0], {}),
    code(W, "Format Error", [220, 0], FORMAT_ERROR),
    node(W, "Telegram: Send Error", "n8n-nodes-base.telegram", 1.2, [440, 0], {
        "chatId": "={{ $json.chat_id }}",
        "text": "={{ $json.text }}",
        "additionalFields": {"appendAttribution": False},
    }, **RETRY),
], link("Error Trigger", "Format Error", "Telegram: Send Error")))

# =====================================================================
# SYS-02 Notify Telegram (sub-workflow)
# =====================================================================
W = "SYS-02"
RESOLVE_CHAT = r"""
// === CONFIG: Telegram chat IDs ===
// Find a chat ID: add the bot to the group, send a message, then open
// https://api.telegram.org/bot<TOKEN>/getUpdates  (group IDs start with -100)
const CHATS = {
  alerts: 'REPLACE_WITH_TELEGRAM_ALERTS_CHAT_ID',
  errors: 'REPLACE_WITH_TELEGRAM_ERRORS_CHAT_ID',
};

// Input: { chat: 'alerts' | 'errors', text: string }
return $input.all().map(item => {
  const { chat = 'alerts', text = '' } = item.json;
  const chatId = CHATS[chat];
  if (!chatId) throw new Error(`Unknown Telegram chat "${chat}"`);
  if (!text) throw new Error('Telegram message text is empty');
  return { json: { chat_id: chatId, text: text.length > 4000 ? text.slice(0, 3990) + '…' : text } };
});
"""

save("SYS-02_notify-telegram.json", workflow(SYS02_ID, "[SYS-02] Notify Telegram", [
    node(W, "When Called by Another Workflow", "n8n-nodes-base.executeWorkflowTrigger", 1.1, [0, 0],
         {"inputSource": "passthrough"}),
    code(W, "Resolve Chat", [220, 0], RESOLVE_CHAT),
    node(W, "Telegram: Send", "n8n-nodes-base.telegram", 1.2, [440, 0], {
        "chatId": "={{ $json.chat_id }}",
        "text": "={{ $json.text }}",
        "additionalFields": {"appendAttribution": False},
    }, **RETRY),
], link("When Called by Another Workflow", "Resolve Chat", "Telegram: Send"), SYS01_ID))

# =====================================================================
# ONB-01 Stripe Payment -> Kickoff
# =====================================================================
W = "ONB-01"

CONFIG = r"""
// =====================================================================
// CONFIG: edit after import. No secrets here (API keys live in n8n credentials).
// =====================================================================
const config = {
  // Client Registry (Google Sheet). ID = the long string in the Sheet URL.
  registry_sheet_id: 'REPLACE_WITH_GOOGLE_SHEET_ID',
  registry_tab: 'Clients',

  // ClickUp
  clickup_list_id: 'REPLACE_WITH_CLICKUP_LIST_ID',
  clickup_template_id: 'REPLACE_WITH_CLICKUP_TASK_TEMPLATE_ID',
  // Optional custom field IDs (GET /api/v2/list/{list_id}/field). Leave '' to skip.
  clickup_custom_fields: {
    client_id: '',
    contact_email: '',
    plan_name: '',
    amount: '',
    paid_at: '', // must be a Date field
  },

  // Slack
  // false = demo on a free Slack plan: create a normal channel and put the workspace
  //         invite link in the welcome email instead of sending a Slack Connect invite.
  slack_connect_enabled: false,
  slack_workspace_invite_url: 'REPLACE_WITH_SLACK_WORKSPACE_INVITE_LINK',
  slack_channel_prefix: 'client-',

  // Stripe Payment Link
  company_custom_field_key: 'company', // key of the "Company name" custom field
  default_plan_name: 'Growth Plan',    // used when the Payment Link has no metadata.plan_name

  // Messages
  agency_name: 'Your Agency',
  sender_name: 'Your Agency Team',
  onboarding_form_url: 'REPLACE_WITH_ONBOARDING_FORM_URL',
  booking_url: 'REPLACE_WITH_CALENDLY_OR_CALCOM_URL',
};

return [{ json: { config, event: $input.first().json } }];
"""

NORMALIZE = r"""
// Turns the Stripe checkout.session.completed event into one Client Registry row.
// Every key below must exist as a column header in the Clients sheet.
const { config, event } = $input.first().json;
const s = event.data?.object ?? {};
const details = s.customer_details ?? {};

const email = (details.email || s.customer_email || '').toLowerCase();
if (!email) throw new Error(`Checkout session ${s.id} has no customer email`);

const companyField = (s.custom_fields ?? []).find(f => f.key === config.company_custom_field_key);
const contactName = details.name || '';

return [{
  json: {
    client_id: 'CL-' + $now.toFormat('yyMMdd-HHmmss'),
    status: 'provisioning',
    company_name: companyField?.text?.value || contactName || email,
    contact_name: contactName,
    contact_email: email,
    plan_name: s.metadata?.plan_name || config.default_plan_name,
    amount: (s.amount_total ?? 0) / 100,
    currency: (s.currency || '').toUpperCase(),
    paid_at: new Date((event.created ?? Date.now() / 1000) * 1000).toISOString(),
    stripe_customer_id: s.customer || '',
    stripe_subscription_id: s.subscription || '',
    stripe_session_id: s.id || '',
  },
}];
"""

PREPARE = r"""
// Collects everything the Slack / email steps need, so their expressions stay simple.
const config = $('Config').first().json.config;
const c = $('Normalize Client').first().json;
const res = $input.first().json;

const taskId = res.id || res.task?.id;
if (!taskId) throw new Error('ClickUp did not return a task id: ' + JSON.stringify(res).slice(0, 500));

const slug = c.company_name.toLowerCase()
  .normalize('NFD').replace(/\p{Diacritic}/gu, '')
  .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  .slice(0, 60) || 'client';
const channelName = `${config.slack_channel_prefix}${slug}-${c.client_id.slice(-6)}`.slice(0, 80);

const firstName = (c.contact_name || '').split(' ')[0] || 'there';

const slackWelcome = [
  `👋 Welcome to ${config.agency_name}, ${firstName}!`,
  '',
  'This is the shared channel between your team and ours. Next steps:',
  `1. Fill in the onboarding form: ${config.onboarding_form_url}`,
  `2. Book your kickoff call: ${config.booking_url}`,
  '',
  'We will post updates and results here. Ask us anything, anytime.',
].join('\n');

const slackLine = config.slack_connect_enabled
  ? 'You will receive a separate Slack invite to our shared channel. Please accept it within 24 hours.'
  : `Join our Slack workspace here: <a href="${config.slack_workspace_invite_url}">${config.slack_workspace_invite_url}</a>`;

const emailHtml = `
<p>Hi ${firstName},</p>
<p>Thank you for choosing ${config.agency_name}! Your payment for <b>${c.plan_name}</b> has been received and we have started setting up your account.</p>
<p><b>Next steps:</b></p>
<ol>
  <li>Fill in the onboarding form: <a href="${config.onboarding_form_url}">${config.onboarding_form_url}</a></li>
  <li>Book your kickoff call: <a href="${config.booking_url}">${config.booking_url}</a></li>
  <li>${slackLine}</li>
</ol>
<p>Talk soon,<br>${config.sender_name}</p>`;

return [{
  json: {
    client_id: c.client_id,
    clickup_task_id: taskId,
    clickup_task_url: `https://app.clickup.com/t/${taskId}`,
    slack_connect_enabled: config.slack_connect_enabled,
    slack_channel_name: channelName,
    slack_welcome_text: slackWelcome,
    email_subject: `Welcome to ${config.agency_name}, ${firstName}! Your next steps`,
    email_html: emailHtml,
  },
}];
"""

CUSTOM_FIELDS = r"""
// One item per configured ClickUp custom field. No IDs configured = no items = branch stops.
const config = $('Config').first().json.config;
const c = $('Normalize Client').first().json;
const { clickup_task_id } = $input.first().json;

const items = [];
for (const [key, fieldId] of Object.entries(config.clickup_custom_fields)) {
  if (!fieldId) continue;
  let value = c[key];
  if (value === undefined || value === '') continue;
  if (key.endsWith('_at')) value = new Date(value).getTime(); // ClickUp dates are ms timestamps
  items.push({ json: { task_id: clickup_task_id, field_id: fieldId, value } });
}
return items;
"""

SLACK_RESULT = r"""
// Slack returns HTTP 200 with { ok: false } on errors, and the HTTP nodes are set to
// continue on failure, so collect problems here instead of failing the whole onboarding.
const out = (name) => {
  try { const n = $(name); return n.isExecuted ? n.first().json : null; } catch { return null; }
};
const errText = (r) => typeof r.error === 'string' ? r.error : (r.error?.message || 'unknown error');

const created = out('Slack: Create Channel');
const invite = out('Slack: Invite (Slack Connect)');
const welcome = out('Slack: Welcome Message');

const problems = [];
for (const [label, r] of [['Create channel', created], ['Slack Connect invite', invite], ['Welcome message', welcome]]) {
  if (r && r.ok !== true) problems.push(`Slack ${label}: ${errText(r)}`);
}

return [{
  json: {
    slack_channel_id: created?.channel?.id || '',
    slack_invite_id: invite?.invite_id || '',
    slack_problems: problems,
  },
}];
"""

REGISTRY_UPDATE = r"""
const p = $('Prepare Provisioning').first().json;
const slack = $('Slack Result').first().json;
const mail = $input.first().json;

const problems = [...slack.slack_problems];
if (!mail.id || mail.error) {
  problems.push('Welcome email: ' + (typeof mail.error === 'string' ? mail.error : (mail.error?.message || 'not sent')));
}

// Keys must match column headers in the Clients sheet (matched on client_id).
return [{
  json: {
    client_id: p.client_id,
    status: problems.length ? 'needs_attention' : 'onboarding',
    clickup_task_id: p.clickup_task_id,
    clickup_task_url: p.clickup_task_url,
    slack_channel_id: slack.slack_channel_id,
    slack_invite_id: slack.slack_invite_id,
    notes: problems.join(' | '),
  },
}];
"""

TELEGRAM_MSG = r"""
const c = $('Normalize Client').first().json;
const p = $('Prepare Provisioning').first().json;
const r = $('Build Registry Update').first().json;
const problems = r.notes ? r.notes.split(' | ') : [];

const lines = [
  '💰 New client paid',
  `${c.company_name} – ${c.plan_name} – ${Number(c.amount).toLocaleString('en-US')} ${c.currency}`,
  `Contact: ${c.contact_name} <${c.contact_email}>`,
  `Client ID: ${c.client_id}`,
  `ClickUp: ${p.clickup_task_url}`,
  `Slack: ${r.slack_channel_id ? '#' + p.slack_channel_name : 'not created'}`,
];
if (problems.length) lines.push('', '⚠️ Needs manual action:', ...problems.map(x => '• ' + x));

return [{ json: { chat: 'alerts', text: lines.join('\n') } }];
"""

STICKY = """## [ONB-01] Stripe Payment → Kickoff
Trigger: Stripe `checkout.session.completed` (paid only, duplicates removed).

1. Add client to **Client Registry** (status `provisioning`)
2. **ClickUp** task from template (+ optional custom fields)
3. **Slack** channel → Slack Connect invite (if enabled) → welcome message
4. **Gmail** welcome email
5. Update registry (`onboarding` or `needs_attention`)
6. **Telegram** alert via SYS-02

Slack and email failures do not stop the run: they are listed in the Telegram alert and in the `notes` column. Any other failure goes to SYS-01.

Edit the **Config** node after import."""

CFG = "$('Config').first().json.config"
PREP = "$('Prepare Provisioning').first().json"

nodes = [
    node(W, "Sticky Note", "n8n-nodes-base.stickyNote", 1, [-60, -480],
         {"content": STICKY, "height": 360, "width": 520}),
    node(W, "Stripe Trigger", "n8n-nodes-base.stripeTrigger", 1, [0, 0],
         {"events": ["checkout.session.completed"]}),
    node(W, "Remove Duplicate Events", "n8n-nodes-base.removeDuplicates", 2, [220, 0], {
        "operation": "removeItemsSeenInPreviousExecutions",
        "logic": "removeItemsWithAlreadySeenKeyValues",
        "dedupeValue": "={{ $json.id }}",
        "options": {},
    }),
    node(W, "Only Paid", "n8n-nodes-base.filter", 2.2, [440, 0], {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{
                "id": nid(W, "cond-paid"),
                "leftValue": "={{ $json.data.object.payment_status }}",
                "rightValue": "paid",
                "operator": {"type": "string", "operation": "equals"},
            }],
            "combinator": "and",
        },
        "options": {},
    }),
    code(W, "Config", [660, 0], CONFIG),
    code(W, "Normalize Client", [880, 0], NORMALIZE),
    sheets(W, "Registry: Add Client", [1100, 0], "append", []),
    http(W, "ClickUp: Create From Template", [1320, 0],
         f"=https://api.clickup.com/api/v2/list/{{{{ {CFG}.clickup_list_id }}}}/taskTemplate/{{{{ {CFG}.clickup_template_id }}}}",
         "={{ JSON.stringify({ name: $('Normalize Client').first().json.company_name + ' – Onboarding' }) }}",
         "clickUpApi", **RETRY),
    code(W, "Prepare Provisioning", [1540, 0], PREPARE),

    # Branch A: custom fields (runs first: higher on canvas)
    code(W, "Build Custom Fields", [1760, -200], CUSTOM_FIELDS),
    http(W, "ClickUp: Set Custom Field", [1980, -200],
         "=https://api.clickup.com/api/v2/task/{{ $json.task_id }}/field/{{ $json.field_id }}",
         "={{ JSON.stringify({ value: $json.value }) }}",
         "clickUpApi", **RETRY),

    # Branch B: Slack -> email -> registry -> Telegram
    http(W, "Slack: Create Channel", [1760, 100],
         "https://slack.com/api/conversations.create",
         "={{ JSON.stringify({ name: $json.slack_channel_name, is_private: false }) }}",
         "slackApi", **CONTINUE),
    node(W, "Slack Connect Enabled?", "n8n-nodes-base.if", 2.2, [1980, 100], {
        "conditions": {
            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
            "conditions": [{
                "id": nid(W, "cond-slack-connect"),
                "leftValue": f"={{{{ {PREP}.slack_connect_enabled }}}}",
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and",
        },
        "options": {},
    }),
    http(W, "Slack: Invite (Slack Connect)", [2200, 0],
         "https://slack.com/api/conversations.inviteShared",
         "={{ JSON.stringify({ channel: $('Slack: Create Channel').first().json.channel?.id, "
         "emails: [$('Normalize Client').first().json.contact_email] }) }}",
         "slackApi", **CONTINUE),
    http(W, "Slack: Welcome Message", [2420, 100],
         "https://slack.com/api/chat.postMessage",
         f"={{{{ JSON.stringify({{ channel: $('Slack: Create Channel').first().json.channel?.id, "
         f"text: {PREP}.slack_welcome_text }}) }}}}",
         "slackApi", **CONTINUE),
    code(W, "Slack Result", [2640, 100], SLACK_RESULT),
    node(W, "Gmail: Welcome Email", "n8n-nodes-base.gmail", 2.1, [2860, 100], {
        "sendTo": "={{ $('Normalize Client').first().json.contact_email }}",
        "subject": f"={{{{ {PREP}.email_subject }}}}",
        "emailType": "html",
        "message": f"={{{{ {PREP}.email_html }}}}",
        "options": {"appendAttribution": False, "senderName": f"={{{{ {CFG}.sender_name }}}}"},
    }, **CONTINUE),
    code(W, "Build Registry Update", [3080, 100], REGISTRY_UPDATE),
    sheets(W, "Registry: Update Client", [3300, 100], "appendOrUpdate", ["client_id"]),
    code(W, "Build Telegram Message", [3520, 100], TELEGRAM_MSG),
    node(W, "Notify Telegram (SYS-02)", "n8n-nodes-base.executeWorkflow", 1.2, [3740, 100], {
        "workflowId": {"__rl": True, "mode": "id", "value": SYS02_ID},
        "options": {"waitForSubWorkflow": True},
    }),
]

connections = link(
    "Stripe Trigger", "Remove Duplicate Events", "Only Paid", "Config", "Normalize Client",
    "Registry: Add Client", "ClickUp: Create From Template", "Prepare Provisioning",
)
connections["Prepare Provisioning"] = {"main": [[to("Build Custom Fields"), to("Slack: Create Channel")]]}
connections.update(link("Build Custom Fields", "ClickUp: Set Custom Field"))
connections.update(link("Slack: Create Channel", "Slack Connect Enabled?"))
connections["Slack Connect Enabled?"] = {"main": [
    [to("Slack: Invite (Slack Connect)")],  # true
    [to("Slack: Welcome Message")],          # false
]}
connections.update(link(
    "Slack: Invite (Slack Connect)", "Slack: Welcome Message", "Slack Result", "Gmail: Welcome Email",
    "Build Registry Update", "Registry: Update Client", "Build Telegram Message", "Notify Telegram (SYS-02)",
))

save("ONB-01_stripe-kickoff.json",
     workflow(ONB01_ID, "[ONB-01] Stripe Payment → Kickoff", nodes, connections, SYS01_ID))

print("ok")
