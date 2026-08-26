# Eventyay Social Media

Eventyay Social Media is a planned plugin for [Eventyay](https://github.com/fossasia/eventyay). It is intended to help event organisers prepare, export, and later publish social media content based on event data such as sessions, speakers, schedules, ticket sales, calls for participation, and online event activity.

The plugin is part of the Eventyay plugin ecosystem and is designed as an extension for organisers who want to promote events more efficiently while keeping control over the final published content.

## Project status

This repository is at the initial project setup stage.

The first development milestone is a configurable CSV generator for social media content. Later milestones can add direct integrations with external social media publishing tools and APIs.

The intended package name is `eventyay-socialmedia` and the intended Python module name is `eventyay_socialmedia`.

## Planned goals

The plugin should make it easier to create reusable social media content from existing Eventyay data.

Planned goals include:

- Generate social media draft content from Eventyay event data.
- Provide configurable CSV exports for manual review and scheduling.
- Support event level and organiser level workflows.
- Help organisers promote speakers, sessions, schedules, ticket sales, calls for participation, and online activities.
- Keep generated content editable before publication.
- Support later integration with social media publishing tools such as Postiz.
- Provide a foundation for future AI assisted text and image card generation.

## Initial milestone: CSV generator

The first implementation milestone should focus on a CSV generator.

The CSV generator should allow organisers to export social media draft rows that can be reviewed, edited, and imported into external publishing tools.

Possible CSV fields include:

- Event name
- Event URL
- Event start date
- Event end date
- Organiser name
- Social media channel
- Post type
- Post text
- Suggested publication date
- Suggested publication time
- Speaker name
- Speaker profile URL
- Session title
- Session abstract
- Session URL
- Session date
- Session time
- Track name
- Room name
- Call for Participation URL
- Ticket URL
- Ticket sales status
- Online event URL
- Image URL or card reference
- Hashtags
- Language
- Status
- Notes

The first version does not need to publish posts directly. It should provide useful export data that organisers can process manually or with external tools.

## Possible content types

The plugin can support different social media content types over time.

Examples include:

- Event announcement posts
- Call for Participation announcement posts
- Call for Participation reminder posts
- Speaker announcement posts
- Session announcement posts
- Schedule release posts
- Ticket sales announcement posts
- Ticket sales reminder posts
- Online event reminder posts
- Live session posts
- Post event thank you posts
- Recording availability posts

## Configuration options

The plugin should allow organisers to configure what data is included in generated content.

Possible configuration options include:

- Enable or disable social media exports for an event.
- Select which content types should be generated.
- Select which Eventyay fields should be included.
- Configure default hashtags.
- Configure default event links.
- Configure language specific templates.
- Configure post timing rules.
- Configure whether draft rows should be generated for all sessions or only selected sessions.
- Configure whether speaker announcements should be generated automatically.
- Configure whether ticket related posts should be generated.

## Template based generation

Generated text should be based on templates so organisers can adjust wording without changing code.

Example templates:

```text
Join us for {event_name} from {event_start_date} to {event_end_date}.
Details and registration: {event_url}
{hashtags}
```

```text
Speaker announcement: {speaker_name} will present "{session_title}" at {event_name}.
Session details: {session_url}
{hashtags}
```

```text
The schedule for {event_name} is now available.
Explore sessions and speakers: {schedule_url}
{hashtags}
```

Templates should support placeholders for event, organiser, speaker, session, schedule, ticket, and online event data.

## Direct Platform Publishing & CSV Scheduler Exports

Eventyay Social Media supports native, direct platform publishing as well as external scheduler CSV export presets:

### 1. Direct Native Publishing
Organizers can connect their social media accounts at the organizer level and publish directly from Eventyay without third-party aggregator services:
- **Bluesky**: Direct post publishing using the AT Protocol (`atproto`) with rich text facets and media upload.
- **Telegram**: Direct bot messaging and channel broadcasts.
- **Mastodon**: Direct status publishing to any Mastodon/Fediverse instance.
- **Twitter / X**: Direct tweet publishing via Twitter API v2.
- **LinkedIn**: Direct post publishing to personal profiles and organization pages.

### 2. External Scheduler CSV Exports
Organizers who prefer using external scheduling suites retain 100% interoperability via Eventyay's built-in CSV export generator. Built-in export presets include:
- **Generic CSV**: Standard multi-field CSV export format.
- **Postiz CSV**: Pre-formatted CSV matching Postiz bulk import structure.
- **Buffer CSV**: Pre-formatted CSV matching Buffer bulk composer format.
- **Hootsuite CSV**: Pre-formatted CSV matching Hootsuite bulk upload structure.

## AI assisted content generation

Future versions may support AI assisted generation of social media text or image card drafts.

Such functionality should remain optional and should keep organisers in control. Generated content should be reviewable before export or publication.

Possible AI assisted features include:

- Short post variants for different platforms
- Speaker announcement text
- Session summary posts
- Hashtag suggestions
- Image card copy
- Multilingual post drafts

## Development setup

Use this setup when developing the plugin together with a local Eventyay installation.

### 1. Set up Eventyay

First make sure you have a working Eventyay development setup.

See the Eventyay repository:

[https://github.com/fossasia/eventyay](https://github.com/fossasia/eventyay)

### 2. Clone this repository

Clone the plugin repository next to your Eventyay checkout or into the local plugin directory used by your Eventyay development setup.

```bash
git clone https://github.com/fossasia/eventyay-socialmedia.git
cd eventyay-socialmedia
```

### 3. Activate the Eventyay virtual environment

Activate the virtual environment used by your Eventyay installation.

Example:

```bash
cd ../eventyay/app
. .venv/bin/activate
```

### 4. Install the plugin in editable mode

After the Python package structure has been added, install the plugin in editable mode from the `eventyay-socialmedia` directory.

```bash
pip install -e .
```

If your Eventyay development setup uses `uv`, you can also use:

```bash
uv pip install -e .
```

### 5. Apply migrations

If the plugin adds database models, run migrations from the Eventyay app directory.

```bash
python manage.py migrate
```

### 6. Compile translations

If translation files are added, compile them from the plugin directory.

```bash
make
```

### 7. Restart Eventyay

Restart the Eventyay development server and worker processes if they are running.

```bash
python manage.py runserver
```

If you use Docker for Eventyay development, restart the relevant containers after installing or changing the plugin.

## Suggested package structure

A possible initial package structure is:

```text
.
├── eventyay_socialmedia/
│   ├── __init__.py        Plugin version
│   ├── apps.py            Eventyay plugin metadata
│   ├── export.py          CSV export generation
│   ├── forms.py           Configuration and export forms
│   ├── models.py          Export settings and optional draft models
│   ├── signals.py         Plugin registration hooks
│   ├── urls.py            Event and control URLs
│   ├── views.py           Export and configuration views
│   ├── templates/         Django templates
│   ├── static/            Static assets
│   └── locale/            Translation files
├── tests/                 Plugin tests
├── pyproject.toml         Python package metadata and dependencies
├── Makefile               Translation and helper commands
├── LICENSE                Apache License 2.0
└── README.md              Project documentation
```

## Suggested Eventyay integration points

The plugin can integrate with Eventyay through organiser and event control views.

Possible integration points include:

- Event settings for enabling social media exports.
- A control view for generating CSV exports.
- A preview page for generated draft posts.
- Export actions for selected sessions or speakers.
- Optional scheduled tasks for recurring draft generation.
- Optional integration settings for external publishing tools.

## Suggested URLs

Possible event control URLs include:

```text
/control/event/<organizer>/<event>/socialmedia/
/control/event/<organizer>/<event>/socialmedia/settings/
/control/event/<organizer>/<event>/socialmedia/export/
/control/event/<organizer>/<event>/socialmedia/preview/
```

The exact URL structure should follow Eventyay plugin conventions once the implementation starts.

## Data model ideas

Possible initial models include:

`SocialMediaExportSettings`
: Stores event specific export settings such as enabled content types, default hashtags, languages, and template choices.

`SocialMediaTemplate`
: Stores reusable text templates for different post types and languages.

`SocialMediaDraft`
: Stores generated draft posts if the plugin later supports preview, approval, or external publishing workflows.

The first CSV only version may start without persistent draft models if exports can be generated on demand.

## Development commands

Run these commands from the plugin repository unless otherwise noted.

Install the plugin in editable mode:

```bash
pip install -e .
```

Compile translations:

```bash
make
```

Regenerate translation files:

```bash
make localegen
```

Run tests:

```bash
pytest
```

## Implementation roadmap

Suggested roadmap:

1. Add Python package structure and Eventyay plugin metadata.
2. Add plugin registration and basic organiser control page.
3. Add CSV export service for selected event data.
4. Add configurable field selection.
5. Add template based post text generation.
6. Add preview before export.
7. Add tests for CSV generation and templates.
8. Add documentation for organisers and developers.
9. Add optional Postiz compatible export format.
10. Add optional API based draft creation for external publishing tools.

## Testing notes

Tests should cover:

- Plugin loading
- CSV export generation
- Field selection
- Template rendering
- Empty or incomplete event data
- Unicode and multilingual text
- Sessions with missing speakers or schedule entries
- Permission checks for organiser control views
- Export download responses

## Production notes

Before enabling the plugin for production use:

- Verify that generated content does not expose private event data.
- Confirm that unpublished sessions or private speaker data are not exported unless explicitly allowed.
- Check permission handling for organiser and team roles.
- Review generated text before publishing.
- Verify exported CSV encoding with the intended publishing tool.
- Confirm that external integrations do not publish content without organiser approval.

## Security and privacy notes

The plugin should treat event, speaker, session, attendee, and ticket information carefully.

The first implementation should avoid exporting personal or private data that is not already intended for public promotion. Direct publishing features should require explicit organiser action or clearly configured approval workflows.

## License

Eventyay Social Media is released under the terms of the Apache License 2.0.

See `LICENSE` for the full license text once the license file has been added to this repository.

## Credits

Maintained by the Eventyay team and FOSSASIA.

## Links

- [Eventyay](https://github.com/fossasia/eventyay)
- [Eventyay Social Media](https://github.com/fossasia/eventyay-socialmedia)
- [Postiz](https://github.com/gitroomhq/postiz-app)
- [FOSSASIA](https://fossasia.org)
