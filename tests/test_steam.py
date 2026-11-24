import html
import json

import httpx
import pytest

from steam_nick_changer import steam

PROFILE = {
    "strPersonaName": "Old",
    "strRealName": "Real",
    "strSummary": "About me",
    "strCustomURL": "me",
    "LocationData": {"locCountryCode": "UA", "locStateCode": "30", "locCityCode": 123},
    "ProfilePreferences": {"hide_profile_awards": 1},
}


def make_client(profile, posts, aliases=None, edit_reply=None):
    """A client talking to a fake Steam; every POST path is appended to posts."""
    current = {"strPersonaName": "Old", **profile}
    aliases = [] if aliases is None else aliases

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/my/edit/info":
            return httpx.Response(302, headers={"Location": "/id/me/edit/info"})
        if request.method == "GET":
            data = html.escape(json.dumps(current), quote=True)
            page = f'<div id="profile_edit_config" data-profile-edit="{data}"></div>'
            return httpx.Response(200, text=page)
        posts.append((path, dict(httpx.QueryParams(request.content.decode()))))
        if path.endswith("/edit"):
            current["strPersonaName"] = posts[-1][1]["personaName"]
            return edit_reply or httpx.Response(200, json={"success": 1})
        if path.endswith("/ajaxclearaliashistory/"):
            aliases.clear()
            return httpx.Response(200, json={"success": 1})
        return httpx.Response(200, json=list(aliases))

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    client.cookies.set("sessionid", "abc", domain="steamcommunity.com")
    return client


def test_change_echoes_profile_and_clears_history():
    posts = []
    aliases = [{"newname": "x"}]
    steam.change_name(make_client(PROFILE, posts, aliases), "New")

    paths = [p for p, _ in posts]
    assert paths[0] == "/id/me/edit"
    assert paths[1] == "/id/me/ajaxclearaliashistory/"
    form = posts[0][1]
    assert form["personaName"] == "New"
    assert form["real_name"] == "Real"
    assert form["summary"] == "About me"
    assert form["customURL"] == "me"
    assert (form["country"], form["state"], form["city"]) == ("UA", "30", "123")
    assert form["sessionID"] == "abc" and form["json"] == "1"
    assert posts[1][1] == {"sessionid": "abc"}
    assert aliases == []


def test_dry_run_posts_nothing_that_changes_data():
    posts = []
    steam.change_name(make_client(PROFILE, posts), "New", dry_run=True)
    assert [p for p, _ in posts] == ["/id/me/ajaxaliases/"]


def test_unreadable_field_stops_before_posting():
    posts = []
    profile = {k: v for k, v in PROFILE.items() if k != "strSummary"}
    with pytest.raises(steam.SteamError):
        steam.change_name(make_client(profile, posts), "New")
    assert posts == []


def test_same_name_skips_save_but_clears_history():
    posts = []
    aliases = [{"newname": "x"}]
    steam.change_name(make_client(PROFILE, posts, aliases), "Old")
    assert [p for p, _ in posts] == [
        "/id/me/ajaxclearaliashistory/",
        "/id/me/ajaxaliases/",
    ]
    assert aliases == []


def test_null_values_become_empty_and_awards_flag_defaults_to_zero():
    posts = []
    profile = {
        **PROFILE,
        "strRealName": None,
        "strSummary": None,
        "strCustomURL": None,
        "LocationData": {"locCountryCode": None, "locStateCode": None, "locCityCode": None},
    }
    del profile["ProfilePreferences"]
    steam.change_name(make_client(profile, posts), "New")
    form = posts[0][1]
    assert (form["real_name"], form["summary"], form["customURL"]) == ("", "", "")
    assert (form["country"], form["state"], form["city"]) == ("", "", "")
    assert form["hide_profile_awards"] == "0"


def test_awards_flag_is_one_when_hidden():
    posts = []
    steam.change_name(make_client(PROFILE, posts), "New")
    assert posts[0][1]["hide_profile_awards"] == "1"


def test_page_without_profile_data_is_a_steam_error_not_login():
    def handler(request):
        return httpx.Response(200, text="<html>something else</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(steam.SteamError) as info:
        steam.change_name(client, "New")
    assert not isinstance(info.value, steam.NotLoggedIn)


def test_non_json_reply_names_status_and_body():
    reply = httpx.Response(503, text="<html>Service   Unavailable</html>")
    with pytest.raises(steam.SteamError, match="503.*Service Unavailable"):
        steam.change_name(make_client(PROFILE, [], edit_reply=reply), "New")


def test_cookies_of_all_domains_are_loaded_and_saved_back(tmp_path):
    path = tmp_path / "auth_state.json"
    cookie = {"path": "/", "expires": 1, "httpOnly": True, "secure": True, "sameSite": "None"}
    state = {
        "cookies": [
            {**cookie, "name": "steamLoginSecure", "value": "old", "domain": "steamcommunity.com"},
            {
                **cookie,
                "name": "steamRefresh_steam",
                "value": "r",
                "domain": "login.steampowered.com",
            },
        ],
        "origins": [],
    }
    path.write_text(json.dumps(state), encoding="utf-8")
    client = steam.open_client(path)
    client.cookies.set("steamLoginSecure", "new", domain="steamcommunity.com", path="/")
    steam.save_cookies(client, path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    values = {c["name"]: c for c in saved["cookies"]}
    assert values["steamLoginSecure"]["value"] == "new"
    assert values["steamLoginSecure"]["httpOnly"] is True
    assert values["steamRefresh_steam"]["domain"] == "login.steampowered.com"
    assert saved["origins"] == []


def test_login_redirect_means_not_logged_in():
    def handler(request):
        return (
            httpx.Response(302, headers={"Location": "/login/home/"})
            if (request.url.path != "/login/home/")
            else httpx.Response(200, text="login")
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(steam.NotLoggedIn):
        steam.change_name(client, "New")
