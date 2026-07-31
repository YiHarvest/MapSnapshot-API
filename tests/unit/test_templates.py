import asyncio

from server.services.templates import render_share_template


def test_render_share_template_injects_task_data_and_static_config() -> None:
    html = asyncio.run(
        render_share_template(
            "national_share.html",
            {
                "taskId": "template-task",
                "regions": [
                    {
                        "name": "杭州市",
                        "adcode": "330100",
                        "level": "city",
                        "value": "8",
                        "center": [120.1, 30.2],
                    }
                ],
                "valueLabel": "状态",
            },
        )
    )

    assert "template-task" in html
    assert "330100" in html
    assert "window._AMapSecurityConfig" in html
