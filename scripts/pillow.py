from PIL import Image, ImageDraw, ImageFont

def render_svg_blueprint():
    # 1. 初始化精确画布
    width, height = 440, 956
    # 工业亮灰背景
    canvas = Image.new("RGBA", (width, height), "#D9D9D9")
    
    # 为了处理具有特定不透明度的元素，我们建立独立的透明图层
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw_base = ImageDraw.Draw(canvas)
    draw_overlay = ImageDraw.Draw(overlay)

    # 2. 绘制机能引导条 (黄条)
    # <rect width="8" height="44" fill="#FFBD44"/>
    draw_base.rectangle([0, 0, 8, 44], fill="#FFBD44")

    # 3. 数据承载底纹 (细灰带)
    # <rect x="8" y="37" width="415" height="7" fill="#B6B5B5"/>
    draw_base.rectangle([8, 37, 8 + 415, 37 + 7], fill="#B6B5B5")

    # 4. 结构外框线 (带倒角的线框)
    # stroke="black" stroke-opacity="0.31" stroke-width="5"
    black_31 = (0, 0, 0, int(255 * 0.31))
    
    # 拆解 SVG Path: M8 3.5 C8 3.5 98.5 3.5 112 3.5 C125.5 3.5 125.5 15.5 125.5 15.5
    # 这实际上是一条水平线 + 一个 90 度圆角
    # 第一段：水平直塞
    draw_overlay.line([(8, 3), (112, 3)], fill=black_31, width=5)
    # 第二段：完美倒角弧线 (利用 SVG 坐标逆推圆心和半径)
    # 从横向 (112, 3) 弯曲到纵向 (125, 15)
    draw_overlay.arc([98, -10, 125, 15], start=0, end=90, fill=black_31, width=5)

    # 5. 右侧极简斜线标尺 (Greebles)
    # M436.5 37 L434 43.5 和 M439.5 37 L437 43.5
    draw_overlay.line([(436.5, 37), (434, 43.5)], fill=black_31, width=1)
    draw_overlay.line([(439.5, 37), (437, 43.5)], fill=black_31, width=1)

    # 6. 文字排版层 (基于 SVG 坐标重构)
    # Figma 将文字变为了矢量集，提取其起始原点和透明度 (fill-opacity="0.52")
    black_52 = (0, 0, 0, int(255 * 0.52))
    
    # 尝试加载默认等宽字体，实际工程请替换为你的设计字体
    try:
        font = ImageFont.truetype("courier.ttf", 10)
    except:
        font = ImageFont.load_default()

    # 第一行文字起点 (M14.3 11.6)，实色 fill="black"
    draw_overlay.text((14.3, 5), "SYSTEM.DATA.INIT", font=font, fill=(0,0,0,255), anchor="lt")
    
    # 第二行文字起点 (M19.7 24)，52%透明度
    draw_overlay.text((19.7, 16), "MODULE_01 // ACTIVE", font=font, fill=black_52, anchor="lt")
    
    # 第三行文字起点 (M21.8 31)，52%透明度
    draw_overlay.text((21.8, 25), "LAT: 45.281, LON: -12.903", font=font, fill=black_52, anchor="lt")

    # 7. 终极合成
    canvas.alpha_composite(overlay)
    
    # 保存结果
    canvas.save("svg_replicated_panel.png")
    print("SVG 级坐标精度面板已复刻完毕！")

if __name__ == "__main__":
    render_svg_blueprint()