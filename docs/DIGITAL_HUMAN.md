# 动态数字人设计

## 结论

首个内置版本采用动态 2D SVG，而不是直接引入 3D。SVG 2 原生支持可缩放矢量图形、动态修改、
CSS 动画和脚本交互，适合以少量受控参数组合卡通头像；页面无需下载模型权重或第三方运行时。
参考 [W3C SVG 2](https://www.w3.org/TR/SVG2/) 和
[W3C SVG 动画说明](https://www.w3.org/TR/SVG/animate.html)。

3D 同样可行，但需要额外准备 glTF 人体模型、材质、骨骼或 Morph Target 动画，并通过类似
Three.js `GLTFLoader`/`AnimationMixer` 的链路加载。它更适合作为后续独立资产管线，而不是当前
本地安装的默认依赖。参考 [Three.js Animation System](https://threejs.org/manual/en/animation-system.html)。

## 当前实现

每个用户会得到一个不可修改、不可删除的“数字人形象设计师”内置 Agent。“设置 → 数字人工作台”向
`POST /api/v1/digital-humans/generate` 提交最多 1000 字的描述，服务端将它确定性映射为闭合参数：

- 人物呈现、肤色、发型、发色和眼睛颜色；
- 服装、服装颜色、配饰、表情和背景；
- 显示名与稳定种子。

服务端不接受或返回用户提供的 SVG、HTML、脚本、URL 和任意颜色值，因此描述不能注入页面标记。
相同描述得到相同参数。前端 `DigitalAvatar.vue` 用这些参数组合内联 SVG，并提供眨眼、呼吸和背景
漂浮动画、暂停控制及 SVG 导出。动画尊重操作系统的 `prefers-reduced-motion` 设置；相关可访问性
行为见 [MDN prefers-reduced-motion](https://developer.mozilla.org/docs/Web/CSS/Reference/At-rules/@media/prefers-reduced-motion)。

## 边界

- 当前是风格化卡通形象，不用于真实人物身份复刻、换脸、口型驱动或生物识别。
- 生成过程完全本地且不需要 LLM/图片模型密钥，不会隐式调用云服务。
- 当前导出 SVG 静态形象；页面动画由应用样式驱动。
- 若以后增加 3D，应单独限制 glTF 来源、文件大小、纹理、外部 URI、脚本扩展和 GPU 资源，并继续
  提供 2D/减少动态效果回退。
