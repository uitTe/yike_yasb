# 天气组件

默认配置使用 `yasb.open_meteo.OpenMeteoWidget`，通过 Open-Meteo 获取天气，无需服务密钥。

## 位置设置

打开天气弹窗，点击“位置设置”，可以搜索城市，也可以填写地点名称、纬度和经度。

- 纬度范围为 `-90` 至 `90`，经度范围为 `-180` 至 `180`。
- 保存后将位置写入程序 `defaults/config.yaml` 中对应组件的 `options.location`。
- 配置保存保留其他字段和 YAML 注释，检测到外部修改时提示重新读取。
- 变更经纬度后会清除原位置天气缓存，避免沿用其他地点的数据。

默认配置示例见 [config.yaml](../src/defaults/config.yaml)。

## 中文界面

设置 `language: zh_CN` 后，天气详情、体感温度、湿度、气压、云量、紫外线指数、预报日期和小时曲线中的“现在”使用简体中文。设置 `language: en` 后使用英文。

`weather_card.show_hourly_forecast` 控制小时预报，`forecast_days` 控制预报天数，`units` 支持 `metric` 和 `imperial`。

## WeatherAPI 组件

项目也保留 `yasb.weather.WeatherWidget`。该组件需要在配置页面填写 WeatherAPI 服务密钥与城市；界面内置文案随项目语言切换。

配置页面的使用方式见 [可视化配置页面](settings-page.md)，语言设置见 [界面语言](language.md)。
