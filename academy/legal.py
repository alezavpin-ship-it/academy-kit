"""Copyright notice of the app. It is fixed: there is no setting, pack field or screen that changes it.

The name is sealed with a checksum. If the notice is edited or removed from the code, the app refuses to open
(see ``verify`` and ``guard``). This stops casual edits; the legal protection is the copyright itself.
"""

from __future__ import annotations

import hashlib
import html

OWNER = "Alejandro Zavala"
YEAR = 2026
_SEAL = "e20a39fc05ee0d500d85f4fbe4300ee4ec6faa596385ef6e7770bc54e2e92c71"  # sha256 of "<YEAR>|<OWNER>"


def verify() -> bool:
    """True while the author and year are the original ones."""
    return hashlib.sha256(f"{YEAR}|{OWNER}".encode("utf-8")).hexdigest() == _SEAL


def notice(lang: str = "en") -> str:
    rights = "Todos los derechos reservados." if lang == "es" else "All rights reserved."
    return f"© {YEAR} {OWNER}. {rights}"


def footer_html(lang: str = "en") -> str:
    return f'<div class="ak-legal" role="contentinfo">{html.escape(notice(lang))}</div>'


def guard(lang: str = "en") -> None:
    """Stops the app when the copyright notice was altered."""
    if verify():
        return
    import streamlit as st

    st.error("El aviso de derechos de autor fue modificado. La app no puede abrirse." if lang == "es"
             else "The copyright notice was modified. The app cannot open.")
    st.stop()
