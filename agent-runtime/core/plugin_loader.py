"""
Plugin Loader - Discovers and loads agent plugins.
"""

import importlib
import importlib.util
import re
from typing import Optional
from pathlib import Path
from loguru import logger

from plugins.base_plugin import BasePlugin


class PluginLoader:
    """Discovers, loads, and manages agent plugins."""

    # Static mapping from agent registry slugs to known plugin slugs.
    # When an agent slug has no exact plugin, this map provides a fallback
    # so that agents with similar capabilities reuse the right plugin.
    AGENT_SLUG_TO_PLUGIN: dict[str, str] = {
        # ── S+ tier ──
        "omniscient":       "omniscient-agent",
        "apex-coder":       "apex-coder",
        "apex-designer":    "design-studio",
        "apex-analyst":     "data-analysis-agent",
        "apex-ops":         "omniscient-agent",
        "apex-researcher":  "research-agent",
        # ── S tier ──
        "sentinel-pro":     "coding-agent",
        "architect":        "coding-agent",
        "nexus-chat":       "communication-agent",
        "mediaforge":       "media-agent",
        "sentinel-watch":   "monitoring-agent",
        "sysforge":         "system-agent",
        "documaster":       "writing-agent",
        # ── A tier ──
        "phantom-designer": "design-studio",
        "dataforge":        "data-analysis-agent",
        "recon":            "research-agent",
        "deployer":         "coding-agent",
        "mailforge":        "communication-agent",
        "audiocraft":       "media-agent",
        "loghound":         "monitoring-agent",
        "netconfig":        "system-agent",
        "copyace":          "writing-agent",
        "testrunner":       "coding-agent",
        "uxaudit":          "design-studio",
        "patentscout":      "research-agent",
        "sqlmaster":        "data-analysis-agent",
        # ── B tier ──
        "scribe":           "writing-agent",
        "taskmaster":       "omniscient-agent",
        "pixelsmith":       "design-studio",
        "meetbot":          "communication-agent",
        "videoclip":        "media-agent",
        "uptimeguard":      "monitoring-agent",
        "diskmanager":      "system-agent",
        "translingo":       "writing-agent",
        "gitflow":          "coding-agent",
        "trendspy":         "research-agent",
        "chartbuilder":     "data-analysis-agent",
        "focuszone":        "omniscient-agent",
        # ── C tier ──
        "codewatch":        "coding-agent",
        "scrappy":          "research-agent",
        "slackops":         "communication-agent",
        "thumbnailgen":     "media-agent",
        "perftracker":      "monitoring-agent",
        "processguard":     "system-agent",
        "colorpal":         "design-studio",
        "factchecker":      "research-agent",
        "csvcleaner":       "data-analysis-agent",
        "custom-agent":     "omniscient-agent",
        # ── B- tier ──
        "quill":            "writing-agent",
        "quicktype":        "coding-agent",
        "screensnap":       "media-agent",
        "filesorter":       "system-agent",
        "clippy":           "omniscient-agent",
        "bashbuddy":        "coding-agent",
        "webwatch":         "research-agent",
        "quickreply":       "communication-agent",
        "iconforge":        "design-studio",
        "envsetup":         "system-agent",
        # ── F tier ──
        "clickbot":         "omniscient-agent",
        "notegrab":         "writing-agent",
        "timer":            "omniscient-agent",
        "sysmon-lite":      "monitoring-agent",
        "linkcheck":        "research-agent",
        "hashcalc":         "system-agent",
        "gifmaker":         "media-agent",
        "pingbot":          "monitoring-agent",
        "grammarfix":       "writing-agent",
    }

    def __init__(self, plugin_dir: str = "plugins"):
        self.plugin_dir = Path(plugin_dir)
        self.plugins: dict[str, BasePlugin] = {}
        self._aliases: dict[str, str] = {}

    @staticmethod
    def _canonical_identifier(value: str) -> str:
        """Normalize user/registry/plugin identifiers into a comparable slug."""
        if not value:
            return ""
        normalized = value.strip().lower()
        normalized = normalized.replace("_", "-").replace(" ", "-")
        normalized = re.sub(r"-agent$", "", normalized)
        normalized = re.sub(r"[^a-z0-9+\-]+", "-", normalized)
        normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
        return normalized

    def _register_alias(self, alias: str, plugin_key: str):
        canonical = self._canonical_identifier(alias)
        if canonical:
            self._aliases[canonical] = plugin_key

    def _register_plugin(self, plugin: BasePlugin, primary_slug: str, module_name: str):
        key = self._canonical_identifier(primary_slug or module_name)
        if not key:
            return

        self.plugins[key] = plugin

        alias_candidates = {
            key,
            primary_slug,
            module_name,
            plugin.slug,
            plugin.name,
            key.replace("-", "_"),
            key.replace("-", " "),
        }
        for alias in alias_candidates:
            self._register_alias(alias, key)

    def discover_plugins(self):
        """Scan plugin directory and load all valid plugins."""
        if not self.plugin_dir.exists():
            logger.warning(f"Plugin directory not found: {self.plugin_dir}")
            return

        for file_path in self.plugin_dir.glob("*_agent.py"):
            try:
                self._load_plugin_file(file_path)
            except Exception as e:
                logger.error(f"Failed to load plugin {file_path.name}: {e}")

        logger.info(
            f"Loaded {len(self.plugins)} plugins: {list(self.plugins.keys())} "
            f"(aliases: {len(self._aliases)})"
        )

    def _load_plugin_file(self, file_path: Path):
        """Load a single plugin file."""
        module_name = file_path.stem
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            return

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find BasePlugin subclasses in the module
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                plugin = attr()
                slug = plugin.slug or module_name.replace("_agent", "")
                self._register_plugin(plugin, slug, module_name)
                logger.debug(
                    f"Loaded plugin: {plugin.name} "
                    f"(primary='{self._canonical_identifier(slug)}', raw='{slug}')"
                )

    def get_plugin(self, identifier: str) -> Optional[BasePlugin]:
        """Get a plugin by slug or name.
        
        Lookup order:
        1. Exact alias match (canonical form)
        2. Direct canonical-key lookup
        3. AGENT_SLUG_TO_PLUGIN static mapping (maps registry slugs → plugin slugs)
        4. Fuzzy substring match
        If nothing matches, logs a warning and returns None.
        """
        if not identifier:
            return None

        canonical = self._canonical_identifier(identifier)

        # Fast path: exact alias lookup.
        plugin_key = self._aliases.get(canonical)
        if plugin_key and plugin_key in self.plugins:
            return self.plugins[plugin_key]

        # Compatibility path: direct lookup by canonicalized key.
        if canonical in self.plugins:
            return self.plugins[canonical]

        # Static agent-slug → plugin-slug mapping
        mapped_slug = self.AGENT_SLUG_TO_PLUGIN.get(canonical)
        if mapped_slug:
            mapped_canonical = self._canonical_identifier(mapped_slug)
            mapped_key = self._aliases.get(mapped_canonical)
            if mapped_key and mapped_key in self.plugins:
                logger.debug(
                    f"Plugin alias-map hit: '{identifier}' -> '{mapped_key}' "
                    f"(via AGENT_SLUG_TO_PLUGIN)"
                )
                return self.plugins[mapped_key]
            if mapped_canonical in self.plugins:
                logger.debug(
                    f"Plugin alias-map hit: '{identifier}' -> '{mapped_canonical}'"
                )
                return self.plugins[mapped_canonical]

        # Fuzzy fallback: substring match against aliases.
        best_key = None
        best_score = -1
        for alias, key in self._aliases.items():
            if canonical in alias or alias in canonical:
                score = min(len(canonical), len(alias))
                if score > best_score:
                    best_score = score
                    best_key = key
        if best_key and best_key in self.plugins:
            logger.debug(
                f"Plugin fuzzy-match: '{identifier}' -> '{best_key}' "
                f"(canonical='{canonical}', score={best_score})"
            )
            return self.plugins[best_key]

        logger.warning(
            f"No plugin found for agent '{identifier}' "
            f"(canonical='{canonical}'). Available plugins: "
            f"{list(self.plugins.keys())}. The agent will use generic execution."
        )
        return None

    def get_plugin_info(self) -> list[dict]:
        """Get info about all loaded plugins."""
        return [
            {
                "slug": slug,
                "name": plugin.name,
                "description": plugin.description,
                "version": plugin.version,
                "capabilities": plugin.capabilities,
            }
            for slug, plugin in self.plugins.items()
        ]

    def register_plugin(self, plugin: BasePlugin, slug: Optional[str] = None):
        """Manually register a plugin."""
        primary = slug or plugin.slug or plugin.name
        self._register_plugin(plugin, primary, primary)
        logger.info(
            f"Registered plugin: {plugin.name} "
            f"({self._canonical_identifier(primary)})"
        )
