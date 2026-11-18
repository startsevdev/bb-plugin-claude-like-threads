# Claude-Like Threads

The original BB chronological sidebar with collapsible Today, Yesterday, recent dates and Older. It keeps BB's thread rows, pinned threads, sections, menus and existing list controls. Today and Yesterday expand to show all their threads. Prior days start with six rows and Older with twenty.

Install with BB:

~~~sh
bb plugin install git:https://github.com/startsevdev/bb-plugin-claude-like-threads.git@v0.1.2
~~~

Select **Claude-Like Threads** under **Settings → Appearance**. The day headers appear in chronological organization with Updated or Created sorting. If needed, run:

~~~sh
bb thread-list-by-day prefs set organizationMode chronological
bb thread-list-by-day prefs set chronologicalSort updated
bb thread-list-by-day prefs set sortDirection descending
~~~

The dist directory contains the installed plugin snapshot, verified with BB 0.49.0. It is based on the bundled BB thread-list plugin (see LICENSE.bb). The original build.py is provided for reference; its patch anchors target the BB version it was developed against. Installation uses the packaged snapshot and does not run this script.
