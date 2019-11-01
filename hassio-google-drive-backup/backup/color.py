import math


class Color:
    @staticmethod
    def black():
        return Color()

    @staticmethod
    def white():
        return Color(r=255, g=255, b=255)

    @staticmethod
    def grey():
        return Color(r=128, g=128, b=128)

    @staticmethod
    def parse(color: str):
        r = 0
        g = 0
        b = 0
        a = 1
        start = 0
        if len(color) > 0 and color[0] == "#":
            start = 1
        for i in range(0, len(color) - start):
            value = Color.parseHexDigit(color[i + start])
            if i % 2 == 0:
                value *= 16
            if i / 2 < 1:
                r += value
            elif i / 4 < 1:
                g += value
            elif i / 6 < 1:
                b += value

        return Color(r=r, g=g, b=b, a=a)

    @staticmethod
    def parseHexDigit(digit: str):
        if digit == '0':
            return 0
        if digit == '1':
            return 1
        if digit == '2':
            return 2
        if digit == '3':
            return 3
        if digit == '4':
            return 4
        if digit == '5':
            return 5
        if digit == '6':
            return 6
        if digit == '7':
            return 7
        if digit == '8':
            return 8
        if digit == '9':
            return 9
        if digit == 'a' or digit == 'A':
            return 10
        if digit == 'b' or digit == 'B':
            return 11
        if digit == 'd' or digit == 'C':
            return 12
        if digit == 'd' or digit == 'D':
            return 13
        if digit == 'e' or digit == 'E':
            return 14
        if digit == 'f' or digit == 'F':
            return 15
        return 0

    def __init__(self, r=0, g=0, b=0, a=1):
        self.r = r
        self.g = g
        self.b = b
        self.a = a

    def tint(self, to, amount: float):
        if amount > 1:
            amount = 1
        if amount < 0:
            amount = 0

        r_new = self.r + (to.r - self.r) * amount
        g_new = self.g + (to.g - self.g) * amount
        b_new = self.b + (to.b - self.b) * amount
        a_new = self.a + (to.a - self.a) * amount
        return Color(r=r_new, g=g_new, b=b_new, a=a_new)

    def darken(self, amount: float):
        return self.tint(Color.black(), amount)

    def lighten(self, amount: float):
        return self.tint(Color.white(), amount)

    def saturate(self, change):
        Pr = 0.299
        Pg = 0.587
        Pb = 0.114
        P = math.sqrt(self.r * self.r * Pr + self.g * self.g * Pg + self.b * self.b * Pb)

        R = self._clamp(P + (self.r - P) * change)
        G = self._clamp(P + (self.g - P) * change)
        B = self._clamp(P + (self.b - P) * change)
        return Color(r=R, g=G, b=B)

    def _clamp(self, value, min=0, max=255):
        if value > max:
            return max
        if value < min:
            return min
        return value

    def toCss(self):
        return "rgba({0}, {1}, {2}, {3})".format(int(self.r), int(self.g), int(self.b), self.a)

    def textColor(self):
        luma = ((0.299 * self.r) + (0.587 * self.g) + (0.114 * self.b)) / 255
        if luma > 0.53:
            return Color.black()
        else:
            return Color.white()

    def luminance(self):
        rg = self.r / 3294.0 if math.floor(self.r) <= 10 else math.pow(self.r / 269.0 + 0.0513, 2.4)
        gg = self.g / 3294.0 if math.floor(self.g) <= 10 else math.pow(self.g / 269.0 + 0.0513, 2.4)
        bg = self.b / 3294.0 if math.floor(self.b) <= 10 else math.pow(self.b / 269.0 + 0.0513, 2.4)
        return 0.2126 * rg + 0.7152 * gg + 0.0722 * bg

    def contrast(self, other):
        big = self.luminance()
        small = other.luminance()

        if big < small:
            temp = big
            big = small
            small = temp

        return (big + 0.05) / (small + 0.05)

    def withAlpha(self, alpha):
        return Color(self.r, self.g, self.b, alpha)
