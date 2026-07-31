import asyncio
import re

from server.services.templates import render_share_template


def test_share_page_uses_common_static_assets() -> None:
    html = asyncio.run(
        render_share_template(
            "national_share.html",
            {
                "taskId": "asset-task",
                "regions": [],
                "valueLabel": "状态",
            },
        )
    )

    assert '<link rel="stylesheet" href="/static/css/share.css"' in html
    assert re.search(
        r'<script src="/static/js/share-common\.js\?v=[0-9a-f]{12}"></script>',
        html,
    )
    assert "<style>" not in html
