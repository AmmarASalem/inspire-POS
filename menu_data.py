"""Menu items transcribed from the Inspire Cafe menu photos (photos/Screenshot_*.png, 2026-07-24).

Each tuple is (category, name, name_ar, price_le).
"""

MENU_ITEMS = [
    # Hot Coffee
    ("Hot Coffee", "Single Espresso", "سينجل اسبريسو", 30),
    ("Hot Coffee", "Double Espresso", "دابل اسبريسو", 40),
    ("Hot Coffee", "American Coffee", "قهوة أمريكاني", 50),
    ("Hot Coffee", "Cappuccino", "كابتشينو", 70),
    ("Hot Coffee", "Latte", "لاتيه", 65),
    ("Hot Coffee", "Latte Pistachio", "لاتيه بستاشيو", 70),
    ("Hot Coffee", "Spanish Latte", "اسبانش لاتيه", 75),
    ("Hot Coffee", "Macchiato", "ميكاتو", 55),
    ("Hot Coffee", "Cortado", "كورتادو", 60),
    ("Hot Coffee", "Flat White", "فلات وايت", 60),
    ("Hot Coffee", "Hot Mocha", "هوت موكا", 70),
    ("Hot Coffee", "White Mocha", "وايت موكا", 70),
    ("Hot Coffee", "Turkish Coffee", "قهوة تركي", 30),
    ("Hot Coffee", "Hazelnut Coffee", "قهوة بندق", 45),
    ("Hot Coffee", "French Coffee", "قهوة فرنساوي", 40),
    ("Hot Coffee", "Nescafe", "نسكافية", 50),

    # Hot Non Coffee
    ("Hot Non Coffee", "Red Tea", "شاي", 15),
    ("Hot Non Coffee", "Tea Kettle", "براد شاي", 40),
    ("Hot Non Coffee", "Green Tea", "شاي اخضر", 20),
    ("Hot Non Coffee", "Flavored Tea", "شاي اطعمه", 25),
    ("Hot Non Coffee", "Anise", "يانسون", 15),
    ("Hot Non Coffee", "Mint", "نعناع", 15),
    ("Hot Non Coffee", "Herbal Cocktail", "كوكتيل اعشاب", 45),
    ("Hot Non Coffee", "Apple Cider", "عصير تفاح", 40),
    ("Hot Non Coffee", "Hot Chocolate Marshmallow", "هوت شوكليت مارشميلو", 60),
    ("Hot Non Coffee", "Hot Chocolate", "هوت شوكلت", 50),
    ("Hot Non Coffee", "Hot Lotus", "هوت لوتس", 60),
    ("Hot Non Coffee", "Hot Chocolate Tiramisu", "هوت شوكليت تيراميسو", 80),

    # Iced Coffee
    ("Iced Coffee", "Iced Latte", "ايس لاتيه", 65),
    ("Iced Coffee", "Iced Spanish Latte", "ايس سبانش لاتيه", 75),
    ("Iced Coffee", "Iced Cappuccino", "ايس كابتشينو", 70),
    ("Iced Coffee", "Iced Mocha", "ايس موكا", 70),
    ("Iced Coffee", "Iced White Mocha", "ايس وايت موكا", 70),
    ("Iced Coffee", "Iced American", "ايس امريكان", 55),
    ("Iced Coffee", "Matcha Latte", "ماتشا لاتيه", 90),
    ("Iced Coffee", "Strawberry Matcha", "ماتشا فراولة", 90),
    ("Iced Coffee", "Mango Matcha", "ماتشا مانجو", 90),

    # Fresh Juices
    ("Fresh Juices", "Mango", "مانجو", 60),
    ("Fresh Juices", "Guava", "جوافة", 55),
    ("Fresh Juices", "Strawberry", "فراولة", 55),
    ("Fresh Juices", "Orange", "برتقال", 60),
    ("Fresh Juices", "Banana with Milk", "موز باللبن", 60),
    ("Fresh Juices", "Watermelon", "بطيخ", 55),
    ("Fresh Juices", "Peach", "خوخ", 55),
    ("Fresh Juices", "Kiwi", "كيوي", 70),
    ("Fresh Juices", "Lemon / Lemon Mint", "ليمون", 40),
    ("Fresh Juices", "Melon", "شمام", 55),
    ("Fresh Juices", "Mango Peach Cocktail", "مانجو خوخ كوكتيل", 70),
    ("Fresh Juices", "Pina Colada", "بيناكولادا", 70),

    # Smoothies
    ("Smoothies", "Smoothie Lemon Mint", "سموزي ليمون نعناع", 50),
    ("Smoothies", "Raspberry Smoothie", "سموزي توت احمر", 60),
    ("Smoothies", "Smoothie Mixed Berry", "سموزي ميكس بيري", 65),
    ("Smoothies", "Smoothie Passion Fruit", "سموزي باشون", 65),
    ("Smoothies", "Smoothie Blue Pinacolada", "سموزي بلوبيناكولادا", 70),
    ("Smoothies", "Smoothie Blueberry", "سموزي توت ازرق", 60),
    ("Smoothies", "Smoothie Blue Ice", "سموزي بلو ايس", 60),
    ("Smoothies", "Smoothie Watermelon", "سموزي بطيخ", 60),

    # Extras
    ("Extras", "Shot", "شوت", 20),
    ("Extras", "Sauce", "صوص", 20),
    ("Extras", "Flavor", "طعم", 20),
    ("Extras", "Ice Cream", "ايس كريم", 30),
    ("Extras", "Whipped Cream", "كريمة مخفوقة", 30),
    ("Extras", "Nutella", "نوتيلا", 20),
    ("Extras", "Milk", "لبن", 20),
    ("Extras", "Honey", "عسل", 20),

    # Milkshakes
    ("Milkshakes", "Vanilla Shake", "فانيليا شيك", 70),
    ("Milkshakes", "Blueberry Vanilla Shake", "توت ازرق فانيليا شيك", 70),
    ("Milkshakes", "Strawberry Shake", "فراولة شيك", 70),
    ("Milkshakes", "Pistachio Shake", "بستاشيو شيك", 85),
    ("Milkshakes", "Mango Shake", "مانجو شيك", 70),
    ("Milkshakes", "Oreo Shake", "اوريو شيك", 85),
    ("Milkshakes", "Lotus Shake", "لوتس شيك", 85),

    # Coffee Frappe
    ("Coffee Frappe", "Vanilla Frappe", "فانيليا فرابية", 80),
    ("Coffee Frappe", "Caramel Frappe", "كراميل فرابية", 80),
    ("Coffee Frappe", "Mocha Frappe", "موكا فرابية", 80),
    ("Coffee Frappe", "Lotus Frappe", "لوتس فرابية", 90),
    ("Coffee Frappe", "White Mocha Frappe", "وايت موكا فرابية", 80),

    # Pancake
    ("Pancake", "Nutella Pancake", "بان كيك نوتيلا", 50),
    ("Pancake", "Lotus Pancake", "بان كيك لوتس", 60),
    ("Pancake", "Pistachio Pancake", "بان كيك بستاشيو", 65),
    ("Pancake", "White and Dark Chocolate Pancake", "بان كيك شوكولاتة بيضاء وغامقة", 60),

    # Soda & Soft Drinks
    ("Soda & Soft Drinks", "Soft Drink", "سوفت درينك", 30),
    ("Soda & Soft Drinks", "Red Bull", "ريدبول", 70),
    ("Soda & Soft Drinks", "Mojito Soda", "موخيتو صودا", 50),
    ("Soda & Soft Drinks", "Mojito Soda Flavor", "موخيتو صودا اطعم", 65),
    ("Soda & Soft Drinks", "Red Bull MixBerry", "ريدبول ميكس بيري", 90),
    ("Soda & Soft Drinks", "Ice Cream Scoop", "بولة ايس كريم", 30),
    ("Soda & Soft Drinks", "Small Water", "ماء صغير", 10),
    ("Soda & Soft Drinks", "Fairouz", "فيروز", 35),
    ("Soda & Soft Drinks", "Berill", "بريل", 45),
]

# Category display order + the source menu photo that illustrates it
CATEGORY_IMAGES = {
    "Hot Coffee": "menu-hot-coffee.webp",
    "Hot Non Coffee": "menu-hot-noncoffee-iced.webp",
    "Iced Coffee": "menu-hot-noncoffee-iced.webp",
    "Fresh Juices": "menu-juices.webp",
    "Smoothies": "menu-smoothies-extras.webp",
    "Extras": "menu-smoothies-extras.webp",
    "Milkshakes": "menu-milkshakes-frappe.webp",
    "Coffee Frappe": "menu-milkshakes-frappe.webp",
    "Pancake": "menu-milkshakes-frappe.webp",
    "Soda & Soft Drinks": "menu-soda.webp",
}

CATEGORY_ORDER = list(CATEGORY_IMAGES.keys())
