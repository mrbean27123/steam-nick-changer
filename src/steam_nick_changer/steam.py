"""Change the Steam profile name and clear the name history over plain HTTP.

Both actions are form POSTs to steamcommunity.com authenticated by the steamLoginSecure and
sessionid cookies, which are read from a Playwright storage_state file. All cookies of the
file are loaded, including the long-lived steamRefresh_steam of login.steampowered.com, so
that Steam's own redirect can renew an expired steamLoginSecure; the renewed cookies are
written back by save_cookies.
"""

import html
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

log = logging.getLogger(__name__)

COMMUNITY = "https://steamcommunity.com"
TIMEOUT = 30.0
CLEAR_ATTEMPTS = 3
CLEAR_PAUSE = 1.0


class SteamError(Exception):
    """Steam refused a request or answered in an unexpected way."""


class NotLoggedIn(SteamError):
    """The saved cookies are missing or no longer accepted by Steam."""


def open_client(auth_state: Path) -> httpx.Client:
    """Create an HTTP client carrying all cookies of a Playwright storage_state file.

    Raises:
        NotLoggedIn: if the file does not exist.
    """
    if not auth_state.exists():
        raise NotLoggedIn(f"{auth_state.name} does not exist.")
    cookies = json.loads(auth_state.read_text(encoding="utf-8"))["cookies"]
    client = httpx.Client(timeout=TIMEOUT, follow_redirects=True)
    for c in cookies:
        client.cookies.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
    return client


def save_cookies(client: httpx.Client, auth_state: Path) -> None:
    """Write the cookies of the client back to the storage_state file.

    Steam may have renewed steamLoginSecure through a redirect during the run. Attributes
    the jar does not track (httpOnly, secure, sameSite) are kept from the file for known
    cookies.
    """
    state = json.loads(auth_state.read_text(encoding="utf-8"))
    known = {(c["name"], c["domain"], c["path"]): c for c in state["cookies"]}
    cookies = []
    for cookie in client.cookies.jar:
        old = known.get((cookie.name, cookie.domain, cookie.path), {})
        cookies.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "expires": cookie.expires if cookie.expires is not None else old.get("expires", -1),
                "httpOnly": old.get("httpOnly", cookie.has_nonstandard_attr("HttpOnly")),
                "secure": old.get("secure", cookie.secure),
                "sameSite": old.get("sameSite", "Lax"),
            }
        )
    state["cookies"] = cookies
    # Write to a sibling file and swap it in, so an interrupted run cannot leave broken JSON.
    tmp = auth_state.with_name(auth_state.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(auth_state)


def _session_id(client: httpx.Client) -> str:
    # The jar can hold several cookies named sessionid (host and domain variants), so the
    # plain cookies.get() would raise on the conflict.
    for cookie in client.cookies.jar:
        if cookie.name == "sessionid" and cookie.value:
            return cookie.value
    raise NotLoggedIn("No sessionid cookie.")


def _snippet(response: httpx.Response) -> str:
    return " ".join(response.text.split())[:200]


def _check(response: httpx.Response) -> None:
    if response.status_code == 429:
        raise SteamError("Steam answered HTTP 429 (too many requests). Try again later.")
    if response.is_error:
        raise SteamError(f"Steam answered HTTP {response.status_code}: {_snippet(response)}")


def _json(response: httpx.Response):
    """Parse a JSON reply, naming the HTTP status and the start of the body if it is not JSON."""
    try:
        return response.json()
    except ValueError as e:
        raise SteamError(
            f"Steam answered HTTP {response.status_code} with a non-JSON body: {_snippet(response)}"
        ) from e


def _read_profile(client: httpx.Client) -> tuple[str, dict]:
    """Return the profile URL and the current profile values from the edit page.

    The values come from the data-profile-edit JSON of the #profile_edit_config element, the
    same source as editProfile in node-steamcommunity:
    https://github.com/DoctorMcKay/node-steamcommunity/blob/master/components/profile.js
    """
    response = client.get(f"{COMMUNITY}/my/edit/info")
    if "/login" in response.url.path:
        raise NotLoggedIn("Steam redirected to the login page.")
    _check(response)

    tag = re.search(r'<[^>]*id="profile_edit_config"[^>]*>', response.text)
    attr = tag and re.search(r'data-profile-edit="([^"]*)"', tag.group())
    if not attr:
        raise SteamError("The profile edit page has no profile data (the page layout changed?).")
    try:
        current = json.loads(html.unescape(attr.group(1)))
    except ValueError as e:
        raise SteamError("The profile data of the edit page is not valid JSON.") from e

    path = urlsplit(str(response.url)).path.rstrip("/").removesuffix("/edit/info")
    if not path.startswith(("/id/", "/profiles/")):
        raise SteamError(f"Unexpected profile page address: {response.url}")
    return COMMUNITY + path, current


def _profile_form(current: dict, session_id: str, name: str) -> dict[str, str]:
    """Build the profileSave form: every current value is echoed back, only the name changes.

    The request overwrites the whole profile, so a value that cannot be read must stop the
    run instead of being posted as empty. Field names follow editProfile in node-steamcommunity
    (components/profile.js) and SaveProfilePayload in ASFEnhance (Profile/WebRequest.cs).
    The weblink fields are not part of the edit page data and are posted empty, as both
    reference implementations do.
    """
    try:
        location = current["LocationData"]
        form = {
            "sessionID": session_id,
            "type": "profileSave",
            "json": "1",
            "personaName": name,
            # Steam sends null for an empty value, which is posted back as an empty string.
            "real_name": current["strRealName"] or "",
            "summary": current["strSummary"] or "",
            "customURL": current["strCustomURL"] or "",
            "country": location["locCountryCode"] or "",
            "state": location["locStateCode"] or "",
            # The city code is a number or a string (ASFEnhance accepts both).
            "city": str(location["locCityCode"] or ""),
        }
    except (KeyError, TypeError) as e:
        raise SteamError(f"Cannot read the current profile value {e}; nothing was changed.") from e
    if not all(isinstance(v, str) for v in form.values()):
        raise SteamError("A current profile value has an unexpected type; nothing was changed.")

    for i in (1, 2, 3):
        form[f"weblink_{i}_title"] = ""
        form[f"weblink_{i}_url"] = ""
    # Profile preference of the same save request, see ASFEnhance.
    # Steam's own form sends 1 or 0 (ASFEnhance Profile/WebRequest.cs).
    preferences = current.get("ProfilePreferences") or {}
    form["hide_profile_awards"] = "1" if preferences.get("hide_profile_awards") else "0"
    return form


def _aliases(client: httpx.Client, profile: str) -> list:
    response = client.post(f"{profile}/ajaxaliases/", headers=_headers(profile))
    _check(response)
    return _json(response)


def _headers(profile: str) -> dict[str, str]:
    return {"Referer": f"{profile}/edit/info", "Origin": COMMUNITY}


def _clear_aliases(client: httpx.Client, profile: str, session_id: str) -> None:
    """Clear the name history and verify it, as the clear reply alone is not trusted."""
    for attempt in range(1, CLEAR_ATTEMPTS + 1):
        response = client.post(
            f"{profile}/ajaxclearaliashistory/",
            data={"sessionid": session_id},
            headers=_headers(profile),
        )
        _check(response)
        if _json(response).get("success") != 1:
            log.warning("Steam did not confirm clearing the name history (attempt %d).", attempt)
        elif not _aliases(client, profile):
            log.info("Name history cleared.")
            return
        time.sleep(CLEAR_PAUSE)
    log.warning("The name history is still not empty after %d attempts.", CLEAR_ATTEMPTS)


def change_name(client: httpx.Client, name: str, *, dry_run: bool = False) -> None:
    """Set the profile name and clear the name history.

    The history is cleared only after the save succeeded, because the previous name enters
    the history on save. If the profile already has this name (an earlier run may have failed
    after the save), only the clearing is done. With dry_run, nothing is posted except the
    read-only alias query, and the form that would be sent is logged without the session id.

    Raises:
        NotLoggedIn: if the cookies are not accepted.
        SteamError: if Steam refuses the change or the current profile cannot be read.
    """
    profile, current = _read_profile(client)
    session_id = _session_id(client)
    already_set = current.get("strPersonaName") == name
    form = _profile_form(current, session_id, name)

    if dry_run:
        if already_set:
            log.info("Dry run. The name is already %r, only the history would be cleared.", name)
        else:
            shown = {**form, "sessionID": "<redacted>"}
            log.info("Dry run. Would POST %s/edit with %s", profile, shown)
        log.info("Dry run. Current name history entries: %d", len(_aliases(client, profile)))
        return

    if already_set:
        log.info("The profile name is already %r, skipping the save.", name)
    else:
        response = client.post(f"{profile}/edit", data=form, headers=_headers(profile))
        _check(response)
        result = _json(response)
        if result.get("success") != 1:
            raise SteamError(f"Steam rejected the new name: {result.get('errmsg') or result}")
        log.info("Profile name saved: %r", name)

        saved = _read_profile(client)[1].get("strPersonaName")
        if saved != name:
            log.warning("Steam stored %r instead of %r (cut at the byte limit).", saved, name)

    _clear_aliases(client, profile, session_id)
