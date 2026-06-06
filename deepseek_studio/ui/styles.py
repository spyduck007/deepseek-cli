"""Textual CSS for the TUI."""

APP_CSS = """
Screen {
    background: #070b11;
    color: #d6deff;
    layout: vertical;
}

Header {
    height: 1;
    background: #101624;
    color: #d6deff;
    text-style: bold;
}

#main {
    height: 1fr;
    layout: horizontal;
}

#sidebar {
    width: 34;
    min-width: 30;
    max-width: 36;
    height: 1fr;
    background: #0d1320;
    border: tall #24324d;
    padding: 1 1;
    scrollbar-size: 1 1;
    scrollbar-color: #38486a #111827;
}

#simple-title {
    width: 100%;
    height: auto;
    color: #7aa2ff;
    text-style: bold;
    margin: 0 0 1 0;
    padding: 0 0;
    text-align: center;
}

#tagline {
    height: auto;
    color: #98a6c7;
    margin: 0 0 1 0;
    text-align: center;
}

#status-card {
    width: 100%;
    height: auto;
    border: round #283858;
    padding: 1 1;
    margin: 1 0 0 0;
    background: #0a0f1a;
    color: #c6d3f5;
}

#token-card {
    width: 100%;
    height: auto;
    border: round #283858;
    padding: 1 2;
    margin: 1 0 0 0;
    background: #0a0f1a;
    color: #c6d3f5;
    text-align: left;
    text-style: none;
}

#chat-shell {
    width: 1fr;
    min-width: 0;
    height: 1fr;
    layout: vertical;
    background: #070b11;
}

#transcript {
    height: 1fr;
    min-height: 0;
    border: tall #24324d;
    background: #050910;
    padding: 1 2;
    scrollbar-size: 1 1;
    scrollbar-color: #38486a #111827;
}

.message {
    width: 100%;
    height: auto;
    margin: 1 0;
    padding: 1 2;
}

.user {
    border: round #4b6cff;
    background: #101a34;
    color: #e5e9ff;
}

.assistant {
    border: round #2f7d5f;
    background: #0d1713;
    color: #e0f2e9;
}

.thinking {
    border: round #444b5f;
    background: #0b0f18;
    color: #7f879a;
}

.tool {
    border: round #6d5f2f;
    background: #171409;
    color: #e7d9a2;
}

.working {
    border: round #34405f;
    background: #0a0e18;
    color: #8b93a7;
}

.agent {
    border: round #345a7a;
    background: #0a121c;
    color: #a9c8ef;
}

.system {
    border: round #594b7a;
    background: #120f1f;
    color: #c9b8ff;
}

#composer {
    height: 14;
    min-height: 10;
    max-height: 16;
    layout: vertical;
    border: tall #24324d;
    background: #0d1320;
    padding: 1 2 1 2;
}

#composer-title {
    height: 1;
    margin: 0 0 1 0;
    color: #8ea9e8;
    text-style: bold;
}

#command-menu {
    width: 100%;
    height: auto;
    max-height: 6;
    margin: 0;
    padding: 0 2;
    border: round #405475;
    background: #0b1220;
    color: #c6d3f5;
    text-style: none;
}

#prompt {
    width: 100%;
    height: 1fr;
    min-height: 3;
    border: round #38527f;
    background: #050910;
    color: #f4f7ff;
    scrollbar-size: 1 1;
    scrollbar-color: #38486a #111827;
}

#prompt:focus {
    border: round #7aa2ff;
}
"""
