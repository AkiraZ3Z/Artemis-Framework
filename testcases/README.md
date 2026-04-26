YAML 用例格式示例

steps:
  - name: "获取用户列表"
    action: "api.call"
    params:
      method: "GET"
      url: "${config.base_url}/users"
    validate:
      - expect: "${response.status_code}"
        to_be: 200
      - expect: "${response.body}"
        to_be: list
      - expect: "len(${response.body})"
        greater_than: 0
    save:
      first_user: "${response[0]}"
      first_user_id: "${response[0].id}"
      first_user_name: "${response[0].name}"

json 格式：
{
  "steps": [
    {
      "name": "获取用户列表",
      "action": "api.call",
      "params": {
        "method": "GET",
        "url": "${config.base_url}/users"
      },
      "validate": [
        {
          "expect": "${response.status_code}",
          "to_be": 200
        },
        {
          "expect": "${response.body}",
          "to_be": "list"
        },
        {
          "expect": "len(${response.body})",
          "greater_than": 0
        }
      ],
      "save": {
        "first_user": "${response[0]}",
        "first_user_id": "${response[0].id}",
        "first_user_name": "${response[0].name}"
      }
    }
  ]
}

python 格式：
steps = [
    {
        "name": "获取用户列表",
        "action": "api.call",
        "params": {
            "method": "GET",
            "url": "${config.base_url}/users"
        },
        "validate": [
            {"expect": "${response.status_code}", "to_be": 200},
            {"expect": "${response.body}", "to_be": "list"},
            {"expect": "len(${response.body})", "greater_than": 0}
        ],
        "save": {
            "first_user": "${response[0]}",
            "first_user_id": "${response[0].id}",
            "first_user_name": "${response[0].name}"
        }
    }
]