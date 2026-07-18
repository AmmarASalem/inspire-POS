"""Menu items transcribed from the Inspire Cafe menu photos (photos/*.webp).

Each tuple is (category, name, name_ar, price_le).
"""

MENU_ITEMS = [
    # Hot Coffee
    ("Hot Coffee", "Single Espresso", "سينجل اسبريسو", 30),
    ("Hot Coffee", "Double Espresso", "دابل اسبريسو", 40),
    ("Hot Coffee", "American Coffee", "قهوة أمريكاني", 50),
    ("Hot Coffee", "Cappuccino", "كابتشينو", 70),
    ("Hot Coffee", "Latte", "لاتيه", 60),
    ("Hot Coffee", "Latte Pistachio", "لاتيه بستاشيو", 75),
    ("Hot Coffee", "Spanish Latte", "اسبانش لاتيه", 75),
    ("Hot Coffee", "Macchiato", "ميكاتو", 50),
    ("Hot Coffee", "Flat White", "فلات وايت", 60),
    ("Hot Coffee", "Cortado", "كورتانو", 55),
    ("Hot Coffee", "Hot Mocha", "هوت موكا", 70),
    ("Hot Coffee", "White Mocha", "وايت موكا", 70),
    ("Hot Coffee", "Turkish Coffee", "قهوة تركي", 25),
    ("Hot Coffee", "Hazelnut Coffee", "قهوة بندق", 40),
    ("Hot Coffee", "French Coffee", "قهوة فرنساوي", 35),
    ("Hot Coffee", "Nescafe", "نسكافية", 50),

    # Hot Non Coffee
    ("Hot Non Coffee", "Red Tea", "شاي", 15),
    ("Hot Non Coffee", "Tea Kettle", "براد شاي", 35),
    ("Hot Non Coffee", "Green Tea", "شاي اخضر", 20),
    ("Hot Non Coffee", "Flavored Tea", "شاي اطعمه", 20),
    ("Hot Non Coffee", "Anise", "يانسون", 15),
    ("Hot Non Coffee", "Mint", "نعناع", 15),
    ("Hot Non Coffee", "Herbal Cocktail", "كوكتيل اعشاب", 45),
    ("Hot Non Coffee", "Apple Cider", "عصير تفاح", 40),
    ("Hot Non Coffee", "Hot Chocolate Marshmallow", "هوت شوكليت مارشميلو", 60),
    ("Hot Non Coffee", "Hot Chocolate", "هوت شوكلت", 50),
    ("Hot Non Coffee", "Hot Lotus", "هوت لوتس", 55),
    ("Hot Non Coffee", "Hot Chocolate Tiramisu", "هوت شوكليت تيراميسو", 75),

    # Iced Coffee
    ("Iced Coffee", "Iced Latte", "ايس لاتيه", 65),
    ("Iced Coffee", "Iced Spanish Latte", "ايس سبانش لاتيه", 75),
    ("Iced Coffee", "Iced Cappuccino", "ايس كابتشينو", 75),
    ("Iced Coffee", "Iced Mocha", "ايس موكا", 75),
    ("Iced Coffee", "Iced White Mocha", "ايس وايت موكا", 70),
    ("Iced Coffee", "Matcha Latte", "ماتشا لاتيه", 120),
    ("Iced Coffee", "Strawberry Matcha", "ماتشا فراولة", 120),
    ("Iced Coffee", "Mango Matcha", "ماتشا مانجو", 120),

    # Smoothies
    ("Smoothies", "Smoothie Lemon Mint", "سموزي ليمون نعناع", 40),
    ("Smoothies", "Smoothie Strawberry", "سموزي فراولة", 65),
    ("Smoothies", "Smoothie Mixed Berry", "سموزي ميكس بيري", 60),
    ("Smoothies", "Smoothie Passion Fruit", "سموزي باشون", 65),
    ("Smoothies", "Smoothie Raspberry", "سموزي راسبيري", 60),
    ("Smoothies", "Smoothie Blueberry", "سموزي توت ازرق", 65),
    ("Smoothies", "Smoothie Blue Ice", "سموزي بلو ايس", 60),
    ("Smoothies", "Smoothie Watermelon", "سموزي بطيخ", 60),

    # Extras
    ("Extras", "Shot", "شوت", 20),
    ("Extras", "Sauce", "صوص", 20),
    ("Extras", "Flavor", "طعم", 20),
    ("Extras", "Ice Cream", "ايس كريم", 25),
    ("Extras", "Honey", "عسل", 20),
    ("Extras", "Whipped Cream", "كريمة مخفوقة", 30),
    ("Extras", "Nuts", "مكسرات", 20),
    ("Extras", "Nutella", "نوتيلا", 20),
    ("Extras", "Milk", "لبن", 15),

    # Milkshakes
    ("Milkshakes", "Vanilla Shake", "فانيليا شيك", 70),
    ("Milkshakes", "Blueberry Vanilla Shake", "توت ازرق فانيليا شيك", 70),
    ("Milkshakes", "Strawberry Shake", "فراولة شيك", 70),
    ("Milkshakes", "Pistachio Shake", "بستاشيو شيك", 85),
    ("Milkshakes", "Mango Shake", "مانجو شيك", 70),
    ("Milkshakes", "Oreo Shake", "اوريو شيك", 85),

    # Coffee Frappe
    ("Coffee Frappe", "Vanilla Coffee Frappe", "فانيليا قهوة فرابية", 80),
    ("Coffee Frappe", "Caramel Frappe", "كراميل فرابية", 80),
    ("Coffee Frappe", "Mocha Frappe", "موكا فرابية", 80),
    ("Coffee Frappe", "Lotus Frappe", "لوتس فرابية", 90),
    ("Coffee Frappe", "White Mocha Frappe", "وايت موكا فرابية", 80),
    ("Coffee Frappe", "Pistachio Frappe", "بستاشيو فرابية", 90),

    # Frappuccino
    ("Frappuccino", "Vanilla Frappuccino", "فانيليا فرابتشينو", 90),
    ("Frappuccino", "Caramel Frappuccino", "كراميل فرابتشينو", 90),
    ("Frappuccino", "Mocha Frappuccino", "موكا فرابتشينو", 90),
    ("Frappuccino", "White Mocha Frappuccino", "وايت موكا فرابتشينو", 90),
    ("Frappuccino", "Pistachio Frappuccino", "بستاشيو فرابتشينو", 95),
    ("Frappuccino", "Lotus Frappuccino", "لوتس فرابتشينو", 95),

    # Fresh Juices
    ("Fresh Juices", "Mango", "مانجو", 50),
    ("Fresh Juices", "Guava", "جوافة", 40),
    ("Fresh Juices", "Strawberry", "فراولة", 45),
    ("Fresh Juices", "Orange", "برتقال", 50),
    ("Fresh Juices", "Banana with Milk", "موز باللبن", 45),
    ("Fresh Juices", "Watermelon", "بطيخ", 45),
    ("Fresh Juices", "Avocado", "أفوكادو", 70),
    ("Fresh Juices", "Cantaloupe", "الشمام", 40),
    ("Fresh Juices", "Kiwi", "كيوي", 70),
    ("Fresh Juices", "Lemon / Lemon Mint", "ليمون", 40),
    ("Fresh Juices", "Mango Peach Cocktail", "مانجو خوخ كوكتيل", 60),
    ("Fresh Juices", "Pina Colada", "بينا كولادا", 60),

    # Refresh Soda & Soft Drinks
    ("Soda & Soft Drinks", "Soft Drink", "مشروب غازي", 35),
    ("Soda & Soft Drinks", "Red Bull", "ريد بول", 70),
    ("Soda & Soft Drinks", "Mojito Soda", "موهيتو صودا", 50),
    ("Soda & Soft Drinks", "Ice Blue Soda", "ايس بلو صودا", 50),
    ("Soda & Soft Drinks", "Red Bull MixBerry", "ريد بول ميكس بيري", 100),
    ("Soda & Soft Drinks", "Sunshine", "صانشاين", 50),
    ("Soda & Soft Drinks", "Cherry Cola", "شيري كولا", 50),
    ("Soda & Soft Drinks", "Sun Rise", "صن رايز", 50),
    ("Soda & Soft Drinks", "Mojito Flavors", "موهيتو بنكهات", 60),
    ("Soda & Soft Drinks", "Ice Cream Scoop", "بولة ايس كريم", 30),
    ("Soda & Soft Drinks", "Small Water", "ماء صغير", 10),
    ("Soda & Soft Drinks", "Berill", "بريل", 45),
]

# Category display order + the source menu photo that illustrates it
CATEGORY_IMAGES = {
    "Hot Coffee": "menu-hot-coffee.webp",
    "Hot Non Coffee": "menu-hot-noncoffee-iced.webp",
    "Iced Coffee": "menu-hot-noncoffee-iced.webp",
    "Smoothies": "menu-smoothies-extras.webp",
    "Extras": "menu-smoothies-extras.webp",
    "Milkshakes": "menu-milkshakes-frappe.webp",
    "Coffee Frappe": "menu-milkshakes-frappe.webp",
    "Frappuccino": "menu-milkshakes-frappe.webp",
    "Fresh Juices": "menu-juices.webp",
    "Soda & Soft Drinks": "menu-soda.webp",
}

CATEGORY_ORDER = list(CATEGORY_IMAGES.keys())
