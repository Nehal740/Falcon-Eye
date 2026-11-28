# User Guide

## Create an account
Open the dashboard and choose **Sign up**. Enter your name, email and a password of at least 10 characters with a letter and a number. A personal workspace is created for you. Five wrong passwords in a row lock the account for 15 minutes.

## First-time guide
A short guide helps you learn what Falcon Eye does, name your workspace, add your first agent, pick a starter policy and see how decisions work. You can skip it and use **Help** whenever you like.

## Workspaces and roles
Each workspace has its own agents, policies, events and approvals. People in other workspaces cannot see yours. Roles: **Owner** (everything, including roles), **Admin** (manage agents, policies and people, decide approvals), **Member** (view everything and decide approvals), **Viewer** (read-only).

## Agents
Open **Agents → Add agent**. Enter a name and description. You get a secret key **once**: copy it straight away. Follow the on-screen steps (see [Agent integration](AGENT_INTEGRATION.md)), then press **Test connection**. You will see **Connected**, or **Not connected yet** with advice. You can edit an agent, turn it off or on, rotate its key (the old key stops working), revoke its key if it may have leaked, or delete it (its history stays in the event log).

## Policies
Open **Policies**. Pick a template or build your own rules (allow, block, ask a human first), then set priority and scope. Anything without a matching rule is blocked. Use the **Policy tester** to try an action safely: nothing is recorded and nothing runs. See [Policies](POLICIES.md).

## Approvals
When a rule says *ask a human first*, the request waits on the **Approvals** page with the agent, action, resource and reason. Owners, admins and members can **Approve** or **Reject**, with an optional note. Each request can be decided only once; requests expire after 24 hours by default. Approving records your decision. The agent still performs the action itself.

## Overview and events
The **Overview** shows agent counts, allowed, blocked and pending totals, the last 24 hours, a 7-day chart, recent events, the approval queue, policy activity and alerts. It refreshes every 10 seconds. **Events** lets you search and filter every decision and open the details.

## AI assistant
Use **Help** or **Ask Falcon Eye**. The assistant answers from this documentation and a summary of your workspace. It cannot change anything and never sees secrets. Without an AI key on the server it shows matching passages from the documentation instead, and says so.

## Settings
Rename the workspace, manage members (owners and admins add people who already have an account), change your password (this signs out other devices), and read the audit log (owners and admins).


## AI Security & Trust panel and email alerts

* The **Overview** page has an *AI Security & Trust* panel. It counts output checks sent to `/v1/verify`
  in the last 7 days (held, blocked, injection and secret signals, unsupported claims). It never shows the checked text.
* **Settings -> Email alerts** turns the "approval waiting" email on or off for you.
