# Eventyay Social Media Plugin

[![CI Tests](https://github.com/fossasia/eventyay-socialmedia/actions/workflows/tests.yml/badge.svg)](https://github.com/fossasia/eventyay-socialmedia/actions/workflows/tests.yml)
[![Code Style](https://github.com/fossasia/eventyay-socialmedia/actions/workflows/style.yml/badge.svg)](https://github.com/fossasia/eventyay-socialmedia/actions/workflows/style.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python: 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](pyproject.toml)

An official automation and direct-publishing plugin for [Eventyay](https://github.com/fossasia/eventyay) (FOSSASIA event management platform).

The Eventyay Social Media plugin streamlines promotional campaigns for event organizers. It automatically transforms live Eventyay database records—Calls for Participation (CFP), confirmed speakers, session schedules, and ticket releases—into targeted social media posts, ready for direct API publishing or bulk export to external schedulers.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Architecture Overview](#architecture-overview)
- [Supported Platforms & Publishing Modes](#supported-platforms--publishing-modes)
  - [Direct Native Publishing](#1-direct-native-publishing)
  - [External Scheduler CSV Exports](#2-external-scheduler-csv-exports)
- [How It Works (Organizer Workflow)](#how-it-works-organizer-workflow)
- [Template Engine & Placeholders](#template-engine--placeholders)
- [Security & Privacy Architecture](#security--privacy-architecture)
- [Installation & Setup](#installation--setup)
- [Configuration Reference](#configuration-reference)
- [Development Setup](#development-setup)
- [Testing](#testing)
- [Known Limitations & Operational Caveats](#known-limitations--operational-caveats)
- [Contributing](#contributing)
- [License](#license)
- [Credits & Links](#credits--links)

---

## Project Overview

Promoting an open-source conference or community event requires coordinating dozens of announcements across multiple platforms—announcing CFPs, highlighting keynote speakers, sharing track agendas, reminding attendees about ticket tiers, and broadcasting live session starts.

Manually drafting and synchronizing these updates across fragmented channels is repetitive, time-consuming, and prone to copy-paste errors.

The **Eventyay Social Media Plugin** integrates directly into the Eventyay control interface to solve this:
1. **Live Data Binding:** Directly queries Eventyay data models (`Submission`, `Speaker`, `Talk`, `Product`, `CFP`) to synthesize scheduled posts.
2. **Multi-Wave Scheduling:** Automatically plans promotional "waves" (e.g., CFP launch, 7-day reminder, 24-hour final call; session countdowns in minutes).
3. **Organizer-Level Account Management:** Connects platform accounts once per organizer and shares them across events with securely encrypted credentials.
4. **Dual Delivery Modes:** Supports zero-friction direct native publishing via background workers or formatted CSV exports for third-party social media aggregators (Postiz, Buffer, Hootsuite).
5. **Full Editorial Control:** Organizers can review, edit, pin, reschedule, exclude, or manually trigger any post before it goes live.

---

## Key Features

- **Direct Native Publishing:** Automated publishing to Telegram, Mastodon, Twitter / X, LinkedIn, and Bluesky without third-party SaaS middleware.
- **Wave-Based Post Generation:** Configurable milestone offsets for 5 content types:
  - **CFP:** Announcement, reminder, and final call based on the submission deadline.
  - **Speakers:** Highlight confirmed speakers with automated biography links and profile avatars.
  - **Sessions:** Track rooms and start-time countdowns (offset by minutes prior to talk start).
  - **Tickets:** Promote active ticket categories, currency, and default pricing tiers.
  - **Schedule:** Broadcast schedule release announcements relative to the event start date.
- **Custom Post Creation:** Draft ad-hoc custom announcements directly inside the event posts table with custom scheduling and attachments.
- **Pinning & Override Protection:** Mark posts as "Pinned" to lock custom copy or timing changes, preventing automated regeneration from overwriting edits.
- **Rich Media & Avatar Handling:** Automatically fetches speaker avatar photos or custom media attachments and uploads them directly to platform APIs.
- **Speaker Social Handle Resolution:** Parses speaker social links (Twitter/X, LinkedIn) and interpolates platform-specific `@handles` into post copy.
- **AT Protocol Richtext Facets:** Generates native byte-offset links and hashtags for Bluesky posts.
- **SSRF & DNS-Rebinding Protection:** Validates all remote media URLs, blocks private/local IP ranges, caps payload size at 10 MB, and uses DNS pinning.
- **Encrypted Credential Storage:** Organizers' API keys and access tokens are encrypted at rest using Fernet symmetric encryption derived from Django's `SECRET_KEY`.
- **Granular Permissions:** Seamlessly integrates with Eventyay team role-based permissions (`can_change_event_settings`, `can_change_organizer_settings`, or `can_manage_social_media`).
- **Comprehensive Publishing Audit Log:** Tracks delivery statuses (`draft`, `scheduled`, `published`, `failed`, `exported`, `excluded`), timestamps, remote post IDs/URLs, and API error traces with manual retry capability.

---

## Architecture Overview

The plugin is structured around modular components responsible for generation, persistence, security, and delivery:

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Eventyay Core Data                            │
│           (Event, Submissions, Speakers, Talks, Products)              │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │     export.build_posts()      │
                     │  - Wave offset calculations   │
                     │  - Template safe formatting   │
                     │  - Speaker handle resolution  │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │   export.sync_posts_to_db()   │
                     │  - Persists SocialMediaPost   │
                     │  - Preserves pinned posts     │
                     │  - Cleans up obsolete drafts  │
                     └───────────────┬───────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │       SocialMediaPost         │
                     │ (DRAFT, SCHEDULED, EXCLUDED)  │
                     └───────────────┬───────────────┘
                                     │
           ┌─────────────────────────┴─────────────────────────┐
           │                                                   │
           ▼ (Manual Review / Export)                          ▼ (Automated Worker)
┌──────────────────────┐                           ┌──────────────────────┐
│  CSV Export Engine   │                           │ Celery Periodic Beat │
│  - Generic           │                           │ publish_scheduled_   │
│  - Postiz            │                           │        posts         │
│  - Buffer            │                           └──────────┬───────────┘
│  - Hootsuite         │                                      │
└──────────────────────┘                                      ▼
                                                   ┌──────────────────────┐
                                                   │ claim_post_for_pub-  │
                                                   │       lishing        │
                                                   │ (select_for_update)  │
                                                   └──────────┬───────────┘
                                                              │
                                                              ▼
                                                   ┌──────────────────────┐
                                                   │  publish_single_post │
                                                   │    (Async Celery)    │
                                                   └──────────┬───────────┘
                                                              │
                    ┌─────────────────┬───────────────────────┼─────────────────┐
                    ▼                 ▼                       ▼                 ▼
             ┌─────────────┐   ┌─────────────┐         ┌─────────────┐   ┌─────────────┐
             │  Telegram   │   │  Mastodon   │         │  Twitter/X  │   │  LinkedIn   │
             │  Provider   │   │  Provider   │         │  Provider   │   │  Provider   │
             └─────────────┘   └─────────────┘         └─────────────┘   └─────────────┘
                                                              │
                                                              ▼
                                                       ┌─────────────┐
                                                       │   Bluesky   │
                                                       │  (atproto)  │
                                                       └─────────────┘
```

### Core Components

| Module | Responsibility |
|---|---|
| `socialmedia/models.py` | Defines `SocialMediaPost` (persisted posts and publishing states) and `SocialMediaAccount` (organizer-level credentials). |
| `socialmedia/export.py` | Extracts live Eventyay objects, calculates wave schedules, formats templates, and provides CSV export presets. |
| `socialmedia/crypto.py` | Encrypts and decrypts sensitive integration tokens at rest using Fernet keys derived from Django `SECRET_KEY`. |
| `socialmedia/providers/` | Pluggable API adapters (`TelegramProvider`, `MastodonProvider`, `TwitterProvider`, `LinkedInProvider`, `BlueskyProvider`) managed by a central registry. |
| `socialmedia/signals.py` | Handles navigation injection, dashboard components, and the periodic scheduling dispatcher (`publish_scheduled_posts`). |
| `socialmedia/tasks.py` | Asynchronous Celery task (`publish_single_post`) executing remote network requests off the main beat thread. |
| `socialmedia/views.py` | Event settings, template management, AJAX post updates, manual publishing triggers, CSV downloads, and account CRUD. |
| `socialmedia/utils.py` | SSRF defenses, private IP network filtering, DNS pinning (`DNSResolverContext`), and local media file fallbacks. |

---

## Supported Platforms & Publishing Modes

### 1. Direct Native Publishing

All direct native providers support credential validation, test messaging, text formatting, and media attachments.

| Platform | Authentication / Credentials | Media Handling | Max Length | Details |
|---|---|---|---|---|
| **Telegram** | Bot API Token (`bot_token`), Target Chat ID (`platform_username` e.g. `@channel` or `-100...`) | `sendPhoto` with caption (JPEG/PNG). URL download or local disk fallback. | 4,096 chars | Markdown formatting supported with automatic plain-text retry if formatting fails. |
| **Mastodon** | Instance Base URL (`api_base_url`), Access Token (`access_token`, scopes: `write:statuses`, `read:accounts`) | Multi-format media upload via `media_post` (JPEG, PNG, GIF, WebP). | 500 chars | Status published via `Mastodon.py` client; works with any standard Fediverse instance. |
| **Twitter / X** | 4-legged OAuth 1.0a: API Key, API Secret, Access Token, Access Token Secret | v1.1 Media Upload API (`upload.twitter.com/1.1`) requires OAuth1 user context. | 280 chars | Published via Twitter API v2 (`/2/tweets`). If media upload encounters transient network errors, URL falls back into tweet text. |
| **LinkedIn** | OAuth 2.0 Access Token (`access_token`, scopes: `w_member_social`, `openid`, `profile`). Author URN (person or organization). | Two-step asset upload (`/v2/assets?action=registerUpload` followed by binary PUT). | 3,000 chars | Targets versioned REST Posts API (`/rest/posts` with `LinkedIn-Version: 202504`), falling back to legacy `ugcPosts`. Personal author URNs are auto-detected via `/v2/me` or `/v2/userinfo`. |
| **Bluesky** | AT Protocol identifier (`handle`), App Password (`app_password`), PDS host URL (default `https://bsky.social`) | Blob upload via `com.atproto.repo.uploadBlob` embedded as `app.bsky.embed.images` (up to 4 images). | 300 graphemes (3,000 bytes) | Generates AT Protocol rich text facets (`app.bsky.richtext.facet`) with exact UTF-8 byte offsets for links and tags. |

> [!WARNING]
> Testing credentials via **Test Connection** for Twitter / X, LinkedIn, and Bluesky publishes a real, public test post on that platform. Ensure you test using appropriate test or staging accounts.

### 2. External Scheduler CSV Exports

For teams using third-party social media suites, the plugin generates pre-formatted CSV exports containing only active/enabled posts:

| Format Preset | Export Columns | Intended Target |
|---|---|---|
| **Generic CSV** | `post_date`, `post_time`, `post_text`, `media_url` | Custom spreadsheets, generic marketing automation workflows. |
| **Postiz** | `content`, `date`, `time`, `media` | Direct bulk upload into [Postiz](https://github.com/gitroomhq/postiz-app). |
| **Buffer** | `text`, `scheduled_at`, `link`, `image` | Buffer bulk composer (`scheduled_at` combines ISO date and time). |
| **Hootsuite** | `date`, `time`, `text`, `link` | Hootsuite bulk scheduler format. |

---

## How It Works (Organizer Workflow)

```
Configure Accounts  ──>  Adjust Settings  ──>  Customize Templates  ──>  Generate Posts  ──>  Review & Publish
(Organizer Level)       (Event Settings)      (Event Templates)        (Live DB Sync)         (Auto or Manual)
```

### Step 1: Connect Social Media Accounts (Organizer Level)
1. Go to your Organizer dashboard in Eventyay.
2. In the sidebar, select **Social Media Accounts**.
3. Click **Add Account**, select your provider (Telegram, Mastodon, Twitter/X, LinkedIn, Bluesky), and provide your credentials.
4. Click **Test Connection** to verify API reachability and access tokens.
5. Accounts configured here are available across all events managed by the organizer.

### Step 2: Configure Event Settings
1. Navigate to your event in the Eventyay Control panel.
2. In the common event sidebar, open **Social Media** → **Settings**.
3. Toggle:
   - **Target Platforms:** Select which platforms to target (e.g., Twitter, Mastodon, Bluesky).
   - **Content Types:** Enable CFP, Speaker, Session, Ticket, or Schedule announcements.
   - **Timing Waves & Offsets:** Configure how many days (or minutes) before the milestone each wave should trigger.
   - **Auto-Publish:** When enabled, the background worker automatically publishes scheduled posts when due. If disabled, posts remain scheduled until manually approved or pinned.
   - **Default Hashtags & Event Link:** Set default event hashtags and optional URL overrides.

### Step 3: Customize Templates
1. Navigate to **Social Media** → **Templates**.
2. Review default templates for each milestone wave.
3. You can set global templates or override copy per platform (e.g., shorter copy for Twitter/Bluesky, richer copy with markdown for Telegram).
4. Forms validate character limits in real time based on platform rules.

### Step 4: Generate and Review Posts
1. Navigate to **Social Media** → **Posts**.
2. Click **Generate Posts**. The plugin queries live event data and synthesizes draft posts according to your wave offsets.
3. Use the filter bar to search by status (`Draft`, `Scheduled`, `Published`, `Failed`, `Excluded`), content type, or platform.
4. Click any post row to edit the copy, upload/replace media URLs, adjust scheduled time, or toggle **Pinned**.

### Step 5: Publishing & Monitoring
- **Automatic Publishing:** If `socialmedia_auto_publish` is active, Eventyay's Celery periodic worker checks for due posts every cycle, acquires a row lock (`select_for_update`), claims the post, and dispatches publishing asynchronously.
- **Manual Publishing:** Click **Publish Now** on any post to publish immediately, bypassing the scheduler.
- **Bulk Actions:** Select multiple posts to perform batch operations: Publish Now, Reschedule, Change Status, or Delete.
- **Publishing Log:** Inspect **Social Media** → **Publishing Log** for a full audit trail showing delivery time, remote post URLs, and detailed provider error stack traces if an API call fails.

---

## Template Engine & Placeholders

The template engine performs safe string formatting without executing arbitrary template logic. Missing keys or extra brackets are safely handled without throwing runtime exceptions.

### Available Tokens by Content Type

| Content Type | Available Tokens | Description |
|---|---|---|
| **CFP** | `{event_name}`, `{cfp_deadline}`, `{cfp_link}`, `{hashtags}` | Promotes CFP deadlines and public submission URLs. |
| **Speaker** | `{event_name}`, `{speaker_name}`, `{speaker_link}`, `{talk_title}`, `{hashtags}`, `{speaker_social_handle}`, `{speaker_twitter}`, `{speaker_linkedin}`, `{speaker_linkedin_url}` | Highlights confirmed speakers, titles, and resolves speaker social handles. |
| **Session** | `{event_name}`, `{talk_title}`, `{talk_room}`, `{talk_start_time}`, `{speaker_names}`, `{talk_link}`, `{hashtags}` | Countdown to talk start time in specific rooms. |
| **Ticket** | `{event_name}`, `{ticket_name}`, `{ticket_price}`, `{ticket_link}`, `{hashtags}` | Promotes active ticket categories and pricing. |
| **Schedule** | `{event_name}`, `{schedule_link}`, `{hashtags}` | Broadcasts publication of the overall agenda. |

### Wave Timing System

Each content type supports multiple waves defined as comma-separated offsets:
- **CFP, Speaker, Ticket, Schedule:** Offset defined in **days** prior to the target milestone date (e.g., `14, 7, 1`).
- **Session:** Offset defined in **minutes** prior to the talk start time (e.g., `60, 15, 0`).

---

## Security & Privacy Architecture

- **Credential Encryption at Rest:** Account tokens, consumer secrets, and app passwords are encrypted using Fernet symmetric encryption (`cryptography.fernet.Fernet`). The encryption key is deterministically derived from Django's `SECRET_KEY` via SHA-256 (`socialmedia/crypto.py`). Plaintext secrets are never stored in the database.
- **SSRF Defense & Network Validation:** When remote media attachments or avatars are fetched for upload to platform APIs, the plugin validates the URL host (`socialmedia/utils.py`):
  - Enforces `http` or `https` schemes.
  - Resolves hostnames and rejects any IP falling inside private, loopback, link-local, multicast, or cloud metadata ranges (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1/128`, `fc00::/7`, `fe80::/10`).
  - Employs **DNS Pinning** (`DNSResolverContext`) to prevent Time-of-Check to Time-of-Use (TOCTOU) DNS rebinding attacks.
  - Enforces a strict 10 MB maximum payload limit on remote media.
- **Path Traversal Guards:** Local media reads are strictly confined to `settings.MEDIA_ROOT` via `os.path.realpath` prefix verification.
- **Race Condition Prevention:** Automated publishing claims rows atomically using `SocialMediaPost.objects.select_for_update(skip_locked=True)` in a database transaction, transitioning status to `EXPORTED` before releasing the lock for asynchronous Celery execution.
- **Permission Scoping:** All event views require authenticated organizers with `can_change_event_settings` or `can_manage_social_media`. Account administration requires organizer permissions (`can_change_organizer_settings` or `can_manage_social_media`).

---

## Installation & Setup

### Prerequisites

- Python 3.12+
- A running [Eventyay](https://github.com/fossasia/eventyay) instance (Django 5.2+, PostgreSQL 15+, Redis 7+)
- Celery worker and Celery beat scheduler

### 1. Install the Plugin

Activate your Eventyay virtual environment and install the plugin in editable mode:

```bash
# Using standard pip
pip install -e /path/to/eventyay-socialmedia

# Or using uv (recommended for Eventyay)
uv pip install -e /path/to/eventyay-socialmedia
```

### 2. Apply Database Migrations

Run database migrations from the Eventyay `app` directory:

```bash
cd /path/to/eventyay/app
python manage.py migrate
```

This creates the `socialmedia_socialmediapost` and `socialmedia_socialmediaaccount` database tables.

### 3. Compile Translations

Compile gettext translation catalogs:

```bash
cd /path/to/eventyay-socialmedia
make
```

### 4. Verify Celery Worker & Beat

Ensure that Eventyay Celery workers and periodic beat runners are running. The periodic dispatcher relies on the `eventyay.common.signals.periodic_task` signal:

```bash
# In your Eventyay operational environment
celery -A eventyay.celery_app worker -l info
celery -A eventyay.celery_app beat -l info
```

---

## Configuration Reference

### Relevant Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | *(Required by Django)* | Used by `crypto.py` to derive the Fernet symmetric encryption key. |
| `CELERY_TASK_ALWAYS_EAGER` | `False` | When set to `True` (e.g. during testing or development), Celery tasks execute synchronously. |
| `MEDIA_ROOT` | *(Eventyay setting)* | Local filesystem root for media files and avatars. |
| `MEDIA_URL` | `/media/` | URL prefix for uploaded media. |
| `DEBUG` | `False` | When `True`, SSRF IP-range validation is bypassed for localhost media testing. |

### Event Settings Keys

These settings are managed automatically via the **Social Media** → **Settings** UI and stored in Eventyay's hierarchical `event.settings`:

| Setting Key | Type | Default | Description |
|---|---|---|---|
| `socialmedia_auto_publish` | bool | `True` | Automatically publish scheduled posts when due. |
| `socialmedia_default_hashtags` | str | `""` | Appended to generated posts via `{hashtags}`. |
| `socialmedia_event_link` | str | `""` | Optional manual override for `{event_link}`. |
| `socialmedia_<platform>_enabled` | bool | `False` | Enable specific platform (`twitter`, `linkedin`, `telegram`, `mastodon`, `bluesky`). |
| `socialmedia_<type>_enabled` | bool | `True` | Enable content types (`cfp`, `speaker`, `session`, `ticket`, `schedule`). |
| `socialmedia_<type>_offsets` | str | *(varies)* | Comma-separated offsets for scheduling waves. |

---

## Development Setup

To develop the plugin alongside Eventyay locally:

### 1. Repository Layout

Place `eventyay` and `eventyay-socialmedia` side-by-side:

```bash
mkdir -p ~/eventyay-workspace
cd ~/eventyay-workspace

git clone https://github.com/fossasia/eventyay.git
git clone https://github.com/fossasia/eventyay-socialmedia.git
```

### 2. Set Up Virtual Environment

Set up the environment using `uv` inside `eventyay/app`:

```bash
cd ~/eventyay-workspace/eventyay/app
uv sync --all-extras --all-groups

# Install the socialmedia plugin into the virtual environment
uv pip install -e ../../eventyay-socialmedia
```

### 3. Run Migrations & Compile Messages

```bash
. .venv/bin/activate
python manage.py migrate
cd ../../eventyay-socialmedia
make
```

### 4. Start Eventyay Development Server

```bash
cd ~/eventyay-workspace/eventyay/app
. .venv/bin/activate
python manage.py runserver
```

Open `http://localhost:8000/control/`, navigate to your event, enable the **Social Media** plugin under **Event Settings** → **Plugins**, and start developing.

---

## Testing

The plugin test suite covers models, encryption, provider APIs, safe URL fetching, Celery tasks, navigation signals, forms, and views using `pytest` and `pytest-django`.

### Running Tests Locally

Run tests from the `eventyay-socialmedia` repository using the virtual environment:

```bash
# Set testing environment variable required by Eventyay settings
EVY_RUNNING_ENVIRONMENT=testing pytest tests

# Run with test coverage
EVY_RUNNING_ENVIRONMENT=testing pytest tests --cov=socialmedia --cov-report=term-missing
```

### Running Specific Test Modules

```bash
# Provider API adapters
EVY_RUNNING_ENVIRONMENT=testing pytest tests/test_providers.py

# Task dispatcher & Celery execution
EVY_RUNNING_ENVIRONMENT=testing pytest tests/test_tasks.py

# Credential encryption
EVY_RUNNING_ENVIRONMENT=testing pytest tests/test_crypto.py

# End-to-end views and workflow overhaul
EVY_RUNNING_ENVIRONMENT=testing pytest tests/test_workflow_overhaul.py
```

### Code Style & Formatting

The codebase enforces strict styling with `ruff` and `pre-commit`:

```bash
# Check code style and imports
ruff check .

# Check code formatting
ruff format --check .

# Run all pre-commit hooks
pre-commit run --all-files
```

---

## Known Limitations & Operational Caveats

1. **Test Message Side Effects:**
   - On **Twitter / X**, **LinkedIn**, and **Bluesky**, triggering **Test Connection** publishes a live post to the platform to confirm write permissions. Ensure test connections are run on authorized test accounts.
2. **Twitter / X Media Upload Requirements:**
   - Twitter's v1.1 Media Upload endpoint strictly requires all four OAuth 1.0a credentials (API Key, API Secret, Access Token, Access Token Secret). Twitter Bearer tokens cannot be used to upload media attachments.
3. **LinkedIn Token Expiration:**
   - LinkedIn OAuth 2.0 user access tokens generally expire after 60 days. When tokens expire, posts fail with HTTP 401/403 errors and must be re-authenticated in the organizer account settings.
4. **Speaker Social Handle Dependency:**
   - The `{speaker_social_handle}` token relies on speakers providing their Twitter/X or LinkedIn profiles in their Eventyay speaker profile. If no matching link exists, the token resolves cleanly to an empty string.
5. **Session Scheduling Dependency:**
   - Session countdown posts require talks to be scheduled in the active Eventyay schedule release. Unscheduled talks fall back to the event start date or can be excluded.

---

## Contributing

We welcome contributions from the community!

1. **Fork & Branch:** Create a feature branch off `dev` or `master` (`git checkout -b feature/my-new-feature`).
2. **Coding Standards:** Follow PEP 8 guidelines, Python 3.12 typing conventions, and keep functions documented. Run `ruff check .` and `ruff format .` before committing.
3. **Add Tests:** If adding a feature or fixing a bug, provide matching unit tests in `tests/`.
4. **Translations:** If adding user-facing strings, mark them with `gettext_lazy` (`_("...")`) and regenerate catalogs with `make localegen`.
5. **Submit a PR:** Push your branch and open a Pull Request describing your changes, motivation, and verification steps.

---

## License

This project is licensed under the **Apache License 2.0**. See the [LICENSE](LICENSE) file for details.

---

## Credits & Links

- Maintained by **FOSSASIA** and the **Eventyay Community**.
- [Eventyay Core Repository](https://github.com/fossasia/eventyay)
- [Eventyay Social Media Plugin](https://github.com/fossasia/eventyay-socialmedia)
- [FOSSASIA Homepage](https://fossasia.org)
