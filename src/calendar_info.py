"""
Calendar, Lunar Calendar, and Solar Terms calculation module.
Pure Python implementation with no external dependencies required.
"""

import datetime

# 农历基础数据表 (1900-2100)
# 每个十六进制数的格式：
# 前4位表示闰月大小与月份大小，后1位表示闰哪个月
LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5d0, 0x14573, 0x052d0, 0x0a9a8, 0x0e950, 0x06aa0,
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b5a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x055c0, 0x0ab60, 0x096d5, 0x092e0,
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04bd7, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63
]

TIAN_GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DI_ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
SHENG_XIAO = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
LUNAR_MONTHS = ["正", "二", "三", "四", "五", "六", "七", "八", "九", "十", "冬", "腊"]
LUNAR_DAYS = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十"
]
WEEKDAYS_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

SOLAR_TERMS_24 = [
    "小寒", "大寒", "立春", "雨水", "惊蛰", "春分",
    "清明", "谷雨", "立夏", "小满", "芒种", "夏至",
    "小暑", "大暑", "立秋", "处暑", "白露", "秋分",
    "寒露", "霜降", "立冬", "小雪", "大雪", "冬至"
]


def _lunar_year_days(year):
    info = LUNAR_INFO[year - 1900]
    days = 0
    for i in range(12):
        days += 30 if (info & (0x10000 >> (i + 1))) else 29
    leap = info & 0xf
    if leap != 0:
        days += 30 if (info & 0x10000) else 29
    return days


def _lunar_month_days(year, month, is_leap=False):
    info = LUNAR_INFO[year - 1900]
    leap = info & 0xf
    if is_leap and leap == month:
        return 30 if (info & 0x10000) else 29
    return 30 if (info & (0x10000 >> month)) else 29


def get_lunar_date(dt: datetime.date):
    """根据公历日期计算农历日期"""
    base = datetime.date(1900, 1, 31)
    offset = (dt - base).days

    year = 1900
    while year < 2100:
        year_days = _lunar_year_days(year)
        if offset < year_days:
            break
        offset -= year_days
        year += 1

    info = LUNAR_INFO[year - 1900]
    leap_month = info & 0xf
    is_leap = False

    month = 1
    while month <= 12:
        m_days = _lunar_month_days(year, month, False)
        if offset < m_days:
            break
        offset -= m_days

        if leap_month == month:
            leap_days = _lunar_month_days(year, month, True)
            if offset < leap_days:
                is_leap = True
                break
            offset -= leap_days

        month += 1

    day = offset + 1

    # 干支年
    tg_idx = (year - 4) % 10
    dz_idx = (year - 4) % 12
    ganzhi = f"{TIAN_GAN[tg_idx]}{DI_ZHI[dz_idx]}"
    sx = SHENG_XIAO[dz_idx]

    month_str = ("闰" if is_leap else "") + LUNAR_MONTHS[month - 1] + "月"
    day_str = LUNAR_DAYS[day - 1] if day <= len(LUNAR_DAYS) else f"{day}日"

    return {
        "year": year,
        "month": month,
        "day": day,
        "is_leap": is_leap,
        "month_str": month_str,
        "day_str": day_str,
        "full_str": f"{month_str}{day_str}",
        "ganzhi": ganzhi,
        "zodiac": sx,
        "year_str": f"{ganzhi}{sx}年"
    }


def get_calendar_info(dt: datetime.date = None):
    """获取完整的日历综合信息"""
    if dt is None:
        dt = datetime.date.today()

    weekday_idx = dt.weekday()
    lunar = get_lunar_date(dt)

    return {
        "date": dt,
        "year": dt.year,
        "month": dt.month,
        "day": dt.day,
        "month_en": dt.strftime("%B"),
        "weekday_cn": WEEKDAYS_CN[weekday_idx],
        "weekday_en": WEEKDAYS_EN[weekday_idx],
        "weekday_short_en": dt.strftime("%a").upper(),
        "date_str": dt.strftime("%Y年%m月%d日"),
        "date_dash": dt.strftime("%Y-%m-%d"),
        "lunar": lunar
    }


if __name__ == "__main__":
    info = get_calendar_info()
    print("Calendar Info:", info)
