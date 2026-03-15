from PIL import Image, ImageDraw, ImageFont

def create_a4_header():
    # 1. 定义 A4 尺寸 (300 DPI 下)
    width, height = 2480, 3508
    
    # 创建纯白色画布
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    # 2. 定义小黄条的参数
    # 矩形左上角坐标 (x0, y0) 和右下角坐标 (x1, y1)
    bar_x0, bar_y0 = 100, 100
    bar_x1, bar_y1 = 800, 250
    yellow_color = (255, 223, 0) # 亮黄色
    
    # 绘制黄色矩形
    draw.rectangle([bar_x0, bar_y0, bar_x1, bar_y1], fill=yellow_color)

    # 3. 添加黑色文字
    text = "HELLO WORLD"
    # 注意：你需要确保系统中有字体文件，或者指定路径
    # 如果是 Windows，通常在 C:\Windows\Fonts\arial.ttf
    try:
        font = ImageFont.truetype("arial.ttf", 80) 
    except:
        font = ImageFont.load_default()

    # 计算文字居中位置（在黄条内）
    text_x = bar_x0 + 50
    text_y = bar_y0 + 40
    
    draw.text((text_x, text_y), text, fill="black", font=font)

    # 保存结果
    image.save("a4_output.png")
    print("图片已生成！")

if __name__ == "__main__":
    create_a4_header()