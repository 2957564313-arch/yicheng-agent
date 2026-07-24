# 可替换校园配置包（Campus Profile）

易程智策的通用能力由程序提供，学校差异放在独立的数据目录中。部署到
另一所高校时，不需要重写 LangGraph 或 FastAPI，复制并替换一套校园
配置包，然后修改环境变量 `APP_DATA_DIR` 即可。

## 配置包组成

```text
campus-profile/
├── campus_profile.json      # 学校、校区、版本和能力声明
├── locations.json           # 地点、别名、经纬度、室内外属性
├── travel_times.json        # 校内静态通勤兜底
├── opening_hours.json       # 可参与硬约束校验的开放时间
├── campus_rules.json        # 高优先级结构化校园规则
├── class_periods.json       # 本校节次与作息
├── campus_timetables.json   # 其他服务时间和特殊规则
├── weather_fallback.json    # 可选的演示或离线天气
└── knowledge/
    ├── official/            # 学生手册、规章制度等正式文件的文本
    ├── curated/             # 人工整理的校园服务知识
    └── imported/            # 导入过程产生的候选内容
```

## 为什么不能只换一份学生手册

- 只替换学生手册：制度问答可以迁移；
- 再提供地点和别名：能够理解本校地点；
- 再提供开放时间与课表：能够校验计划是否可执行；
- 再提供坐标或通勤表：能够完成本校时空联合规划；
- 再配置地图、天气接口：能够使用动态环境信息。

因此，对外应描述为“校园配置包可替换”，而不是“上传任意知识库即可
自动适配全部规划能力”。

## 切换方式

在部署环境的 `.env` 中设置：

```dotenv
APP_DATA_DIR=/absolute/path/to/campus-profile
```

启动前运行：

```text
python scripts/validate_static_data.py
```

校验通过后重启服务。当前比赛版本一次加载一个校园配置包；同一服务
同时面向多所学校的动态租户切换属于后续扩展。

## 数据优先级

1. 用户本轮明确要求；
2. 已核验结构化校园规则；
3. 实时地图和天气；
4. 正式制度文件检索；
5. 人工整理但尚待官方复核的知识；
6. 静态路线和演示数据兜底。

冲突时不允许用低优先级知识覆盖高优先级硬约束。

## 动态服务配置

非敏感的校区参数保存在 `campus_profile.json`：

```json
{
  "external_services": {
    "amap": {
      "search_city": "杭州",
      "campus_query": "杭州电子科技大学下沙校区",
      "weather_adcode": "330114"
    }
  }
}
```

API Key 不属于校园配置包，只能通过部署环境变量提供。其他学校替换配置
时，应同步修改搜索城市、校区查询词和天气行政区编码。

地点名称明确时，可以使用高德 POI 入口坐标；“实验室”“食堂”等存在多个
候选的泛称，应绑定默认地点、要求用户补充，或保留静态通勤兜底，不能自动
采用距离学校很远的同名地点。
