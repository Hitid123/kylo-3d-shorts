"""SessionStart hook: copy the ElevenLabs key from the plugin settings (stored in the OS keychain by Claude Code)
to ~/.config/kylo-3d-shorts/elevenlabs.key (mode 600), where eleven.py reads it. Prints nothing (hook output
would land in the conversation)."""
import os

k = os.environ.get("CLAUDE_PLUGIN_OPTION_ELEVENLABS_API_KEY", "").strip()
if k:
    path = os.path.expanduser("~/.config/kylo-3d-shorts/elevenlabs.key")
    try:
        cur = open(path).read().strip() if os.path.exists(path) else ""
        if cur != k:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            old = os.umask(0o077)
            try:
                with open(path, "w") as f:
                    f.write(k)
            finally:
                os.umask(old)
            os.chmod(path, 0o600)
    except OSError:
        pass
