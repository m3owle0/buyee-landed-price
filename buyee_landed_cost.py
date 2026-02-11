#!/usr/bin/env python3
"""
Buyee Landed Cost Calculator
Calculates accurate total landed cost for Buyee packages to US addresses.
"""

import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
import json
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Exchange rate API (free tier)
EXCHANGE_RATE_API = "https://api.exchangerate-api.com/v4/latest/JPY"

# US Customs rates (as of 2025)
US_TARIFF_RATE_JAPAN = 0.15  # 15% baseline tariff
US_DUTY_THRESHOLD = 0  # No de minimis threshold as of Aug 2025


@dataclass
class PackageInfo:
    """Package information extracted from Buyee"""
    item_price_jpy: float
    declared_value_jpy: float
    weight_kg: float
    length_cm: float
    width_cm: float
    height_cm: float
    domestic_shipping_jpy: float = 0.0
    buyee_service_fee_jpy: float = 0.0
    item_name: str = ""
    package_id: str = ""


@dataclass
class ShippingCost:
    """Shipping cost breakdown"""
    method: str
    cost_jpy: float
    cost_usd: float
    delivery_days: int = 0


@dataclass
class LandedCost:
    """Complete landed cost breakdown"""
    item_price_jpy: float
    item_price_usd: float
    domestic_shipping_jpy: float
    domestic_shipping_usd: float
    buyee_service_fee_jpy: float
    buyee_service_fee_usd: float
    international_shipping_jpy: float
    international_shipping_usd: float
    us_customs_duty_usd: float
    us_customs_tax_usd: float
    total_jpy: float
    total_usd: float
    exchange_rate: float
    shipping_method: str


class BuyeeLandedCostCalculator:
    """Main calculator class"""
    
    def __init__(self, destination_address: str, destination_zip: str):
        self.destination_address = destination_address
        self.destination_zip = destination_zip
        self.exchange_rate = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_exchange_rate(self) -> float:
        """Get current JPY to USD exchange rate"""
        try:
            response = requests.get(EXCHANGE_RATE_API, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data['rates']['USD']
        except Exception as e:
            print(f"Warning: Could not fetch exchange rate, using fallback 0.0067: {e}")
            return 0.0067  # Fallback rate (~150 JPY = 1 USD)
    
    def is_item_link(self, buyee_link: str) -> bool:
        """Check if link is an item/product link vs package link"""
        parsed = urlparse(buyee_link)
        path = parsed.path.lower()
        return ('/item/' in path or '/auction/' in path or 
                'yahoo' in buyee_link.lower() or 'mercari' in buyee_link.lower() or
                'rakuma' in buyee_link.lower())
    
    def detect_clothing_category(self, item_name: str, item_description: str = "") -> str:
        """
        Detect clothing category from item name and description.
        Returns: category name (e.g., 't_shirt', 'boots', 'pants', etc.)
        """
        text = (item_name + " " + item_description).lower()
        
        # Footwear
        if any(word in text for word in ['boot', 'sneaker', 'shoe', 'sandal', 'loafer', 'スニーカー', 'ブーツ', '靴']):
            return 'footwear'
        
        # Outerwear (jackets, coats)
        if any(word in text for word in ['jacket', 'coat', 'blazer', 'parka', 'bomber', 'ジャケット', 'コート']):
            return 'outerwear'
        
        # Pants
        if any(word in text for word in ['pant', 'jean', 'trouser', 'パンツ', 'ジーンズ', 'デニム']):
            return 'pants'
        
        # T-shirts and tops
        if any(word in text for word in ['t-shirt', 'tshirt', 'tee', 'shirt', 'top', 'blouse', 'tシャツ', 'シャツ']):
            return 't_shirt'
        
        # Hoodies and sweatshirts
        if any(word in text for word in ['hoodie', 'sweatshirt', 'sweater', 'pullover', 'フーディ', 'スウェット']):
            return 'hoodie'
        
        # Dresses and skirts
        if any(word in text for word in ['dress', 'skirt', 'ドレス', 'スカート']):
            return 'dress'
        
        # Accessories (bags, wallets, etc.)
        if any(word in text for word in ['bag', 'wallet', 'purse', 'backpack', 'バッグ', '財布']):
            return 'accessories'
        
        # Jewelry and small accessories
        if any(word in text for word in ['jewelry', 'necklace', 'ring', 'bracelet', 'watch', 'アクセサリー', '時計']):
            return 'jewelry'
        
        # Default to general clothing if no specific category found
        return 'general'
    
    def estimate_package_dimensions_from_category(self, category: str) -> Tuple[float, float, float]:
        """
        Estimate package dimensions based on clothing category.
        Returns: (length, width, height) in cm
        """
        category_dimensions = {
            'footwear': (35.0, 25.0, 15.0),      # Boots, sneakers - shoe box size
            'outerwear': (45.0, 35.0, 10.0),     # Jackets, coats - flat but large
            'pants': (40.0, 30.0, 5.0),          # Pants - folded flat
            't_shirt': (30.0, 25.0, 3.0),        # T-shirts - very flat
            'hoodie': (35.0, 30.0, 8.0),         # Hoodies - thicker than t-shirts
            'dress': (40.0, 30.0, 5.0),          # Dresses - similar to pants
            'accessories': (25.0, 20.0, 10.0),   # Bags, wallets - medium size
            'jewelry': (15.0, 10.0, 5.0),        # Small items
            'general': (35.0, 25.0, 10.0)        # Default for unknown clothing
        }
        
        return category_dimensions.get(category, category_dimensions['general'])
    
    def estimate_weight_from_category(self, category: str) -> float:
        """
        Estimate package weight based on clothing category.
        Returns weight in kg
        """
        category_weights = {
            'footwear': 1.2,      # Boots/sneakers: ~1.2kg (shoes are heavy)
            'outerwear': 0.8,     # Jackets/coats: ~0.8kg
            'pants': 0.4,         # Pants: ~0.4kg
            't_shirt': 0.2,       # T-shirts: ~0.2kg
            'hoodie': 0.6,         # Hoodies: ~0.6kg
            'dress': 0.5,          # Dresses: ~0.5kg
            'accessories': 0.3,    # Bags/wallets: ~0.3kg
            'jewelry': 0.1,        # Jewelry: ~0.1kg
            'general': 0.4         # Default: ~0.4kg
        }
        
        return category_weights.get(category, category_weights['general'])
    
    def extract_item_info(self, buyee_link: str) -> PackageInfo:
        """
        Extract item information from Buyee item/product link.
        This is for items that haven't been purchased yet.
        """
        print(f"Extracting item information from: {buyee_link}")
        
        parsed = urlparse(buyee_link)
        item_id = ""
        
        # Try to extract item ID (supports Rakuma, Mercari, Yahoo Auctions, etc.)
        if '/item/' in parsed.path:
            # Handle Rakuma format: /rakuma/item/[ID]
            if '/rakuma/item/' in parsed.path:
                match = re.search(r'/rakuma/item/([^/?]+)', parsed.path)
            else:
                # Handle other formats: /item/[platform]/[ID] or /item/[ID]
                match = re.search(r'/item/[^/]+/([^/?]+)', parsed.path)
            if match:
                item_id = match.group(1)
        
        try:
            response = self.session.get(buyee_link, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            package_info = PackageInfo(
                item_price_jpy=0.0,
                declared_value_jpy=0.0,
                weight_kg=0.0,
                length_cm=0.0,
                width_cm=0.0,
                height_cm=0.0,
                package_id=item_id
            )
            
            # Extract item name (with Rakuma-specific selectors)
            title_selectors = [
                'h1.product-title',
                'h1.item-title',
                '.rakuma-item-title',
                '.item-title',
                'h1',
                '.product-name',
                '.item-name',
                '[data-testid="item-title"]',
                'title'
            ]
            for selector in title_selectors:
                try:
                    if '.' in selector or '#' in selector or '[' in selector:
                        elem = soup.select_one(selector)
                    else:
                        elem = soup.find(selector.split('.')[0])
                    if elem:
                        name = elem.get_text(strip=True)
                        # Clean up title (remove "Buyee" suffix if present)
                        if name:
                            name = re.sub(r'\s*-\s*Buyee.*$', '', name, flags=re.IGNORECASE)
                            package_info.item_name = name.strip()
                            break
                except:
                    continue
            
            # Look for price in various formats
            # Try JSON-LD structured data first
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        # Check for price in structured data
                        if 'offers' in data:
                            offers = data['offers']
                            if isinstance(offers, dict) and 'price' in offers:
                                price = float(str(offers['price']).replace(',', ''))
                                if 100 <= price <= 10000000:
                                    package_info.item_price_jpy = price
                                    package_info.declared_value_jpy = price
                            elif isinstance(offers, list) and len(offers) > 0:
                                # Handle list of offers
                                for offer in offers:
                                    if isinstance(offer, dict) and 'price' in offer:
                                        price = float(str(offer['price']).replace(',', ''))
                                        if 100 <= price <= 10000000:
                                            package_info.item_price_jpy = price
                                            package_info.declared_value_jpy = price
                                            break
                except Exception as e:
                    pass
            
            # Look for price in HTML (including Rakuma-specific elements)
            if package_info.item_price_jpy == 0:
                # Check platform type
                is_rakuma = 'rakuma' in buyee_link.lower()
                is_yahoo = 'yahoo' in buyee_link.lower() or 'auction' in buyee_link.lower()
                is_mercari = 'mercari' in buyee_link.lower()
                
                # Try meta tags first (often most reliable)
                meta_price = soup.find('meta', property='product:price:amount')
                if meta_price and meta_price.get('content'):
                    try:
                        price = float(meta_price['content'].replace(',', ''))
                        if 100 <= price <= 10000000:
                            package_info.item_price_jpy = price
                            package_info.declared_value_jpy = price
                    except:
                        pass
                
                # Try data attributes
                if package_info.item_price_jpy == 0:
                    price_elements = soup.find_all(attrs={'data-price': True})
                    for elem in price_elements:
                        try:
                            price = float(elem.get('data-price', '').replace(',', ''))
                            if 100 <= price <= 10000000:
                                package_info.item_price_jpy = price
                                package_info.declared_value_jpy = price
                                break
                        except:
                            continue
                
                # Try CSS selectors - different approach for Rakuma vs others
                if package_info.item_price_jpy == 0:
                    if is_rakuma:
                        # For Rakuma, use specific Buyee Rakuma price selectors
                        rakuma_selectors = [
                            '.attrContainer__price',  # Main price element on Rakuma pages
                            'dl.attrContainer__priceCompo',  # Price component container
                            'div[class*="attrContainer__price"]',
                            'span[class*="price"]',
                            'div[class*="price"]',
                            '.item-price',
                            '.product-price'
                        ]
                        for selector in rakuma_selectors:
                            try:
                                price_elems = soup.select(selector)
                                for price_elem in price_elems:
                                    price_text = price_elem.get_text(strip=True)
                                    # Look for price with yen symbol or YEN
                                    if '円' in price_text or 'YEN' in price_text.upper():
                                        # Match patterns like "13,000 YEN" or "13,000円"
                                        price_match = re.search(r'(\d{1,3}(?:[,，]\d{3}){0,3})\s*(?:円|YEN)', price_text, re.IGNORECASE)
                                        if price_match:
                                            price_str = price_match.group(1).replace(',', '').replace('，', '')
                                            price = float(price_str)
                                            if 100 <= price <= 10000000:
                                                package_info.item_price_jpy = price
                                                package_info.declared_value_jpy = price
                                                break
                                if package_info.item_price_jpy > 0:
                                    break
                            except:
                                continue
                    else:
                        # For Mercari/Yahoo, first remove recommended items from DOM
                        is_mercari = 'mercari' in buyee_link.lower()
                        
                        # Remove recommended items sections completely
                        for elem in soup.select('.recommendItem, .recommend-item, [class*="recommendItem"], [class*="recommend-item"], [class*="similar"]'):
                            elem.decompose()
                        
                        # Try Yahoo auction selectors first (most specific)
                        if is_yahoo:
                            yahoo_selectors = [
                                '.current_price',  # Main Yahoo auction price (confirmed working)
                                'div.current_price',
                                '.price-tax',  # Price with tax info
                                'div[class*="auction"] div[class*="price"]',
                                'div[class*="goodsDetail"] div[class*="price"]'
                            ]
                            for selector in yahoo_selectors:
                                try:
                                    price_elem = soup.select_one(selector)
                                    if price_elem:
                                        price_text = price_elem.get_text(strip=True)
                                        if '円' in price_text or 'JPY' in price_text or 'YEN' in price_text.upper() or '¥' in price_text:
                                            price_match = re.search(r'(\d{1,3}(?:[,，]\d{3}){0,3})\s*(?:円|YEN|JPY)', price_text, re.IGNORECASE)
                                            if price_match:
                                                price_str = price_match.group(1).replace(',', '').replace('，', '')
                                                price = float(price_str)
                                                if 100 <= price <= 10000000:
                                                    package_info.item_price_jpy = price
                                                    package_info.declared_value_jpy = price
                                                    break
                                except:
                                    continue
                        
                        # Try specific Mercari selectors
                        elif is_mercari:
                            mercari_selectors = [
                                '.m-goodsDetail__price',  # Main Mercari item price (confirmed working)
                                'div.m-goodsDetail__price',
                                'div.itemDetail__price',
                                'div[class*="itemDetail"] div[class*="price"]:not([class*="recommend"])',
                                '.itemDetail__priceValue',
                                'div.itemDetail__inner div[class*="price"]'
                            ]
                            for selector in mercari_selectors:
                                try:
                                    price_elem = soup.select_one(selector)
                                    if price_elem:
                                        price_text = price_elem.get_text(strip=True)
                                        if '円' in price_text or 'JPY' in price_text or 'YEN' in price_text.upper() or '¥' in price_text:
                                            price_match = re.search(r'(\d{1,3}(?:[,，]\d{3}){0,3})\s*(?:円|YEN|JPY)', price_text, re.IGNORECASE)
                                            if price_match:
                                                price_str = price_match.group(1).replace(',', '').replace('，', '')
                                                price = float(price_str)
                                                if 100 <= price <= 10000000:
                                                    package_info.item_price_jpy = price
                                                    package_info.declared_value_jpy = price
                                                    break
                                except:
                                    continue
                        
                        # If still not found, try general selectors (recommended items already removed)
                        if package_info.item_price_jpy == 0:
                            price_selectors = [
                                '.item-price',
                                '.product-price',
                                '[data-testid="price"]',
                                '.price-value',
                                'div[class*="itemDetail"]',
                                'div[class*="ItemDetail"]'
                            ]
                            found_prices = []
                            for selector in price_selectors:
                                try:
                                    price_elems = soup.select(selector)
                                    for price_elem in price_elems:
                                        # Double-check: skip if contains recommend in any ancestor
                                        ancestors = []
                                        parent = price_elem.parent
                                        while parent and len(ancestors) < 5:
                                            ancestors.append(' '.join(parent.get('class', [])))
                                            parent = parent.parent
                                        if any('recommend' in ' '.join(ancestors).lower() for _ in [1]):
                                            continue
                                        
                                        price_text = price_elem.get_text(strip=True)
                                        if '円' in price_text or 'JPY' in price_text or 'YEN' in price_text.upper() or '¥' in price_text:
                                            price_match = re.search(r'(\d{1,3}(?:[,，]\d{3}){0,3})\s*(?:円|YEN|JPY)', price_text, re.IGNORECASE)
                                            if price_match:
                                                price_str = price_match.group(1).replace(',', '').replace('，', '')
                                                price = float(price_str)
                                                if 100 <= price <= 10000000:
                                                    found_prices.append(price)
                                except:
                                    continue
                            
                            # Use the largest price found (main item price is usually largest)
                            if found_prices:
                                package_info.item_price_jpy = max(found_prices)
                                package_info.declared_value_jpy = package_info.item_price_jpy
                
                # Fallback to pattern matching - improved logic to avoid recommended items
                if package_info.item_price_jpy == 0:
                    price_patterns = [
                        r'(\d{1,3}(?:[,，]\d{3})*)\s*円',
                        r'¥\s*(\d{1,3}(?:[,，]\d{3})*)',
                        r'JPY\s*(\d{1,3}(?:[,，]?\d{3})*)',
                        r'(\d{1,3}(?:[,，]\d{3})*)\s*YEN',
                    ]
                    
                    # Get page text but exclude recommended items section
                    # Remove recommended items HTML before searching
                    for elem in soup.select('.recommendItem, .recommend-item, [class*="recommend"]'):
                        elem.decompose()  # Remove recommended items from DOM
                    
                    page_text = soup.get_text()
                    
                    # Find all price matches
                    all_prices = []
                    for pattern in price_patterns:
                        matches = re.findall(pattern, page_text, re.IGNORECASE)
                        for match in matches:
                            try:
                                price_str = str(match).replace(',', '').replace('，', '')
                                price = float(price_str)
                                if 100 <= price <= 10000000:  # Reasonable price range
                                    all_prices.append(price)
                            except ValueError:
                                continue
                    
                    if all_prices:
                        # Remove duplicates and sort
                        all_prices = sorted(set(all_prices))
                        
                        # Platform-specific price selection
                        if is_rakuma and len(all_prices) > 1:
                            # For Rakuma, filter out shipping prices (usually < 2000 JPY)
                            filtered_prices = [p for p in all_prices if p >= 2000]
                            if filtered_prices:
                                package_info.item_price_jpy = max(filtered_prices)
                            else:
                                package_info.item_price_jpy = max(all_prices)
                        elif is_yahoo:
                            # For Yahoo auctions, use largest price (buyout price is usually largest)
                            # Filter out very small prices that might be shipping or fees
                            filtered_prices = [p for p in all_prices if p >= 5000]
                            if filtered_prices:
                                package_info.item_price_jpy = max(filtered_prices)
                            else:
                                package_info.item_price_jpy = max(all_prices)
                        elif is_mercari:
                            # For Mercari, use largest price (main item is usually largest)
                            filtered_prices = [p for p in all_prices if p >= 1000]
                            if filtered_prices:
                                package_info.item_price_jpy = max(filtered_prices)
                            else:
                                package_info.item_price_jpy = max(all_prices)
                        else:
                            # Default: use largest price
                            filtered_prices = [p for p in all_prices if p >= 1000]
                            if filtered_prices:
                                package_info.item_price_jpy = max(filtered_prices)
                            else:
                                package_info.item_price_jpy = max(all_prices)
                        
                        package_info.declared_value_jpy = package_info.item_price_jpy
            
            # Try to extract weight/dimensions from description
            weight_patterns = [
                r'重量[：:]\s*(\d+\.?\d*)\s*[kg]',
                r'重さ[：:]\s*(\d+\.?\d*)\s*[kg]',
                r'(\d+\.?\d*)\s*kg',
                r'(\d+\.?\d*)\s*g',
            ]
            
            dimension_patterns = [
                r'サイズ[：:]\s*(\d+\.?\d*)\s*×\s*(\d+\.?\d*)\s*×\s*(\d+\.?\d*)',
                r'(\d+\.?\d*)\s*×\s*(\d+\.?\d*)\s*×\s*(\d+\.?\d*)\s*cm',
                r'(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*cm',
            ]
            
            page_text = soup.get_text()
            
            # Extract weight
            for pattern in weight_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    try:
                        weight = float(matches[0])
                        if 'g' in pattern and weight > 10:  # Likely grams if > 10
                            weight = weight / 1000
                        if 0.01 <= weight <= 50:  # Reasonable weight range
                            package_info.weight_kg = weight
                            break
                    except (ValueError, IndexError):
                        continue
            
            # Extract dimensions
            for pattern in dimension_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    try:
                        dims = matches[0] if isinstance(matches[0], tuple) else matches[0]
                        length = float(dims[0])
                        width = float(dims[1])
                        height = float(dims[2])
                        if all(0.1 <= d <= 200 for d in [length, width, height]):
                            package_info.length_cm = length
                            package_info.width_cm = width
                            package_info.height_cm = height
                            break
                    except (ValueError, IndexError, TypeError):
                        continue
            
            # If we couldn't extract weight/dimensions, estimate from clothing category
            if package_info.weight_kg == 0 or package_info.length_cm == 0:
                # Detect clothing category from item name
                category = self.detect_clothing_category(package_info.item_name, "")
                
                if package_info.weight_kg == 0:
                    package_info.weight_kg = self.estimate_weight_from_category(category)
                    print(f"Estimated weight: {package_info.weight_kg} kg (category: {category})")
                
                if package_info.length_cm == 0:
                    length, width, height = self.estimate_package_dimensions_from_category(category)
                    package_info.length_cm = length
                    package_info.width_cm = width
                    package_info.height_cm = height
                    print(f"Estimated dimensions: {length}×{width}×{height} cm (category: {category})")
            
            # Estimate domestic shipping based on weight (from category or extracted)
            if package_info.weight_kg > 0:
                if package_info.weight_kg < 0.3:
                    package_info.domestic_shipping_jpy = 800  # ~$5.18 for very small items
                elif package_info.weight_kg < 0.5:
                    package_info.domestic_shipping_jpy = 1000  # ~$6.50
                else:
                    package_info.domestic_shipping_jpy = 1200  # ~$7.76 (most common)
                print(f"Estimated domestic shipping: {package_info.domestic_shipping_jpy} JPY")
            elif package_info.item_price_jpy > 0:
                # Fallback: estimate based on category if weight not available
                category = self.detect_clothing_category(package_info.item_name, "")
                estimated_weight = self.estimate_weight_from_category(category)
                if estimated_weight < 0.3:
                    package_info.domestic_shipping_jpy = 800
                elif estimated_weight < 0.5:
                    package_info.domestic_shipping_jpy = 1000
                else:
                    package_info.domestic_shipping_jpy = 1200
                print(f"Estimated domestic shipping: {package_info.domestic_shipping_jpy} JPY (based on category: {category})")
            
            return package_info
            
        except Exception as e:
            print(f"Error extracting item info: {e}")
            raise
    
    def extract_package_info(self, buyee_link: str) -> PackageInfo:
        """
        Extract package information from Buyee link.
        Supports both item/product pages and package detail pages.
        """
        # Check if it's an item link or package link
        if self.is_item_link(buyee_link):
            return self.extract_item_info(buyee_link)
        
        print(f"Extracting package information from: {buyee_link}")
        
        # Parse the URL
        parsed = urlparse(buyee_link)
        
        # Try to get package ID from URL
        package_id = ""
        if 'package' in parsed.path:
            match = re.search(r'package[\/\-]?(\d+)', parsed.path)
            if match:
                package_id = match.group(1)
        
        try:
            response = self.session.get(buyee_link, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try to extract information from the page
            # Buyee package pages have various formats, so we'll try multiple approaches
            
            package_info = PackageInfo(
                item_price_jpy=0.0,
                declared_value_jpy=0.0,
                weight_kg=0.0,
                length_cm=0.0,
                width_cm=0.0,
                height_cm=0.0,
                package_id=package_id
            )
            
            # Extract item name
            title_elem = soup.find('h1') or soup.find('title')
            if title_elem:
                package_info.item_name = title_elem.get_text(strip=True)
            
            # Look for price information (various formats)
            price_patterns = [
                r'(\d+[,，]\d+|\d+)\s*円',
                r'JPY\s*(\d+[,，]?\d*)',
                r'\$\s*(\d+\.?\d*)',
            ]
            
            # Look for weight/dimension information
            weight_patterns = [
                r'(\d+\.?\d*)\s*kg',
                r'(\d+\.?\d*)\s*g',
            ]
            
            dimension_patterns = [
                r'(\d+\.?\d*)\s*×\s*(\d+\.?\d*)\s*×\s*(\d+\.?\d*)\s*cm',
                r'(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*x\s*(\d+\.?\d*)\s*cm',
            ]
            
            page_text = soup.get_text()
            
            # Extract prices
            for pattern in price_patterns:
                matches = re.findall(pattern, page_text)
                if matches:
                    try:
                        price_str = matches[0].replace(',', '').replace('，', '')
                        package_info.item_price_jpy = float(price_str)
                        package_info.declared_value_jpy = package_info.item_price_jpy
                        break
                    except ValueError:
                        continue
            
            # Extract weight
            for pattern in weight_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    try:
                        weight = float(matches[0])
                        if 'g' in pattern:
                            weight = weight / 1000  # Convert to kg
                        package_info.weight_kg = weight
                        break
                    except ValueError:
                        continue
            
            # Extract dimensions
            for pattern in dimension_patterns:
                matches = re.findall(pattern, page_text, re.IGNORECASE)
                if matches:
                    try:
                        dims = matches[0]
                        package_info.length_cm = float(dims[0])
                        package_info.width_cm = float(dims[1])
                        package_info.height_cm = float(dims[2])
                        break
                    except ValueError:
                        continue
            
            # If we couldn't extract automatically, return what we have
            # User will need to provide missing information
            return package_info
            
        except Exception as e:
            print(f"Error extracting package info: {e}")
            raise
    
    def calculate_volumetric_weight(self, length: float, width: float, height: float) -> float:
        """Calculate volumetric weight in kg (Buyee formula)"""
        if length <= 0 or width <= 0 or height <= 0:
            return 0.0
        return (length * width * height) / 5000
    
    def calculate_consolidated_shipping(self, package_infos: list, shipping_method: str = "EMS") -> Tuple[float, float, float, float]:
        """
        Calculate shipping for consolidated packages.
        Returns: (total_weight_kg, max_length_cm, max_width_cm, total_height_cm)
        Uses simplified consolidation - assumes packages can be stacked efficiently.
        """
        if not package_infos:
            return (0.0, 0.0, 0.0, 0.0)
        
        # Sum weights
        total_weight = sum(p.weight_kg for p in package_infos if p.weight_kg > 0)
        
        # For dimensions, use largest length/width and sum heights (simplified stacking)
        max_length = max((p.length_cm for p in package_infos if p.length_cm > 0), default=0.0)
        max_width = max((p.width_cm for p in package_infos if p.width_cm > 0), default=0.0)
        total_height = sum(p.height_cm for p in package_infos if p.height_cm > 0)
        
        # If dimensions are missing, estimate based on weight
        if max_length == 0 or max_width == 0 or total_height == 0:
            # Estimate dimensions based on total weight
            if total_weight < 0.5:
                max_length, max_width, total_height = 30.0, 20.0, 15.0
            elif total_weight < 1.0:
                max_length, max_width, total_height = 40.0, 30.0, 20.0
            elif total_weight < 2.0:
                max_length, max_width, total_height = 50.0, 40.0, 25.0
            else:
                max_length, max_width, total_height = 60.0, 50.0, 30.0
        
        return (total_weight, max_length, max_width, total_height)
    
    def estimate_international_shipping(self, weight_kg: float, length: float, 
                                       width: float, height: float) -> Dict[str, ShippingCost]:
        """
        Estimate international shipping costs using Buyee's actual rates.
        Based on real shipping data analysis from Buyee orders.
        """
        volumetric_weight = self.calculate_volumetric_weight(length, width, height)
        chargeable_weight = max(weight_kg, volumetric_weight)
        
        # Actual Buyee shipping rates (in JPY) based on real order data
        # Exchange rate used: 1 JPY = $0.006470 USD
        shipping_options = {}
        
        # FedEx Air rates (most commonly used, based on actual data)
        # Actual costs observed: $34.94 (5,400 JPY), $53.57 (8,278 JPY), $81.52 (12,600 JPY)
        if chargeable_weight <= 0.3:
            fedex_air_cost = 5400  # ~$35 for small items
        elif chargeable_weight <= 0.5:
            fedex_air_cost = 6500  # ~$42
        elif chargeable_weight <= 1.0:
            fedex_air_cost = 8278  # ~$53.57 (most common)
        elif chargeable_weight <= 1.5:
            fedex_air_cost = 10000  # ~$65
        elif chargeable_weight <= 2.0:
            fedex_air_cost = 12600  # ~$81.52 (observed for heavier items)
        else:
            fedex_air_cost = 12600 + (chargeable_weight - 2.0) * 3000
        
        shipping_options['FedEx Air'] = ShippingCost(
            method='FedEx Air',
            cost_jpy=fedex_air_cost,
            cost_usd=0.0,
            delivery_days=3
        )
        
        # EMS rates (typically cheaper than FedEx Air)
        ems_cost = fedex_air_cost * 0.75  # EMS is typically ~75% of FedEx Air
        
        shipping_options['EMS'] = ShippingCost(
            method='EMS',
            cost_jpy=ems_cost,
            cost_usd=0.0,
            delivery_days=5
        )
        
        # FedEx Economy (cheaper but slower)
        fedex_economy = fedex_air_cost * 0.85  # ~85% of FedEx Air
        
        shipping_options['FedEx Economy'] = ShippingCost(
            method='FedEx Economy',
            cost_jpy=fedex_economy,
            cost_usd=0.0,
            delivery_days=7
        )
        
        # DHL (similar to FedEx Air)
        dhl_cost = fedex_air_cost * 0.95  # ~95% of FedEx Air
        
        shipping_options['DHL'] = ShippingCost(
            method='DHL',
            cost_jpy=dhl_cost,
            cost_usd=0.0,
            delivery_days=4
        )
        
        # Buyee Air Delivery (Buyee's own air delivery service, typically similar to FedEx Air)
        buyee_air_cost = fedex_air_cost * 0.90  # ~90% of FedEx Air (slightly cheaper)
        
        shipping_options['Buyee Air Delivery'] = ShippingCost(
            method='Buyee Air Delivery',
            cost_jpy=buyee_air_cost,
            cost_usd=0.0,
            delivery_days=4
        )
        
        return shipping_options
    
    def calculate_buyee_service_fee(self, item_price_jpy: float, platform: str = "general") -> float:
        """
        Calculate Buyee service fees based on actual fee structure.
        Based on real Buyee order data analysis (exchange rate: 1 JPY = $0.006470):
        Actual observed fees:
        - 8,980 JPY item → 425 JPY fee (4.73% of item price)
        - 9,500 JPY item → 725 JPY fee (7.63% of item price)
        - 9,800 JPY item → 790 JPY fee (8.06% of item price)
        - 15,000 JPY item → 1,075 JPY fee (7.17% of item price)
        
        Using average percentage approach for accuracy
        """
        # Use tiered total percentage based on observed data
        if item_price_jpy < 9000:
            # Lower tier: ~4.7% total
            total_fee = item_price_jpy * 0.0473
        elif item_price_jpy < 10000:
            # Mid tier: ~7.6-8.1% total (average ~7.8%)
            total_fee = item_price_jpy * 0.078
        else:
            # Higher tier: ~7.2% total
            total_fee = item_price_jpy * 0.0717
        
        # Round to nearest JPY
        return round(total_fee)
    
    def calculate_us_customs(self, declared_value_usd: float) -> Tuple[float, float]:
        """
        Calculate US customs duties and taxes.
        Returns: (duty_amount, tax_amount)
        Based on actual Buyee data: 15% duty on item price only (not including shipping)
        """
        # 15% tariff on declared value (item price only, not shipping)
        duty = declared_value_usd * US_TARIFF_RATE_JAPAN
        
        # Processing fee is always $5.00 (observed in all actual orders)
        processing_fee = 5.0 if declared_value_usd > 0 else 0.0
        
        return duty, processing_fee
    
    def calculate_landed_cost(self, buyee_link: str, 
                             shipping_method: str = "EMS",
                             manual_weight_kg: Optional[float] = None,
                             manual_length_cm: Optional[float] = None,
                             manual_width_cm: Optional[float] = None,
                             manual_height_cm: Optional[float] = None,
                             manual_price_jpy: Optional[float] = None) -> LandedCost:
        """
        Calculate complete landed cost for a Buyee package or item.
        
        Args:
            buyee_link: URL to Buyee item/product page or package page
            shipping_method: Preferred shipping method (EMS, FedEx Air, FedEx Economy, DHL)
            manual_*: Optional manual overrides if automatic extraction fails
        """
        # Get exchange rate
        self.exchange_rate = self.get_exchange_rate()
        print(f"Current exchange rate: 1 JPY = ${self.exchange_rate:.6f} USD")
        
        # Extract package information
        try:
            package_info = self.extract_package_info(buyee_link)
        except Exception as e:
            print(f"Warning: Could not extract package info automatically: {e}")
            print("Please provide manual values or check the link.")
            package_info = PackageInfo(
                item_price_jpy=manual_price_jpy or 0.0,
                declared_value_jpy=manual_price_jpy or 0.0,
                weight_kg=manual_weight_kg or 0.0,
                length_cm=manual_length_cm or 0.0,
                width_cm=manual_width_cm or 0.0,
                height_cm=manual_height_cm or 0.0
            )
        
        # Use manual overrides if provided
        if manual_weight_kg:
            package_info.weight_kg = manual_weight_kg
        if manual_length_cm:
            package_info.length_cm = manual_length_cm
        if manual_width_cm:
            package_info.width_cm = manual_width_cm
        if manual_height_cm:
            package_info.height_cm = manual_height_cm
        if manual_price_jpy:
            package_info.item_price_jpy = manual_price_jpy
            package_info.declared_value_jpy = manual_price_jpy
        
        # Calculate Buyee service fee if not already included
        if package_info.buyee_service_fee_jpy == 0:
            # Determine platform for fee calculation
            platform = "general"
            if 'rakuma' in buyee_link.lower():
                platform = "rakuma"
            elif 'mercari' in buyee_link.lower():
                platform = "mercari"
            elif 'yahoo' in buyee_link.lower() or 'auction' in buyee_link.lower():
                platform = "yahoo"
            
            package_info.buyee_service_fee_jpy = self.calculate_buyee_service_fee(
                package_info.item_price_jpy, platform
            )
        
        # Estimate international shipping
        shipping_options = self.estimate_international_shipping(
            package_info.weight_kg,
            package_info.length_cm,
            package_info.width_cm,
            package_info.height_cm
        )
        
        if shipping_method not in shipping_options:
            shipping_method = "EMS"  # Default
            print(f"Warning: {shipping_method} not available, using EMS")
        
        selected_shipping = shipping_options[shipping_method]
        selected_shipping.cost_usd = selected_shipping.cost_jpy * self.exchange_rate
        
        # Convert JPY to USD using exchange rate (never extract USD from page)
        item_price_usd = package_info.item_price_jpy * self.exchange_rate
        domestic_shipping_usd = package_info.domestic_shipping_jpy * self.exchange_rate
        buyee_service_fee_usd = package_info.buyee_service_fee_jpy * self.exchange_rate
        international_shipping_usd = selected_shipping.cost_jpy * self.exchange_rate
        
        # Calculate US customs
        declared_value_usd = package_info.declared_value_jpy * self.exchange_rate
        duty_usd, tax_usd = self.calculate_us_customs(declared_value_usd)
        
        # Calculate totals in both JPY and USD
        total_jpy = (package_info.item_price_jpy + package_info.domestic_shipping_jpy + 
                    package_info.buyee_service_fee_jpy + selected_shipping.cost_jpy)
        total_usd = (item_price_usd + domestic_shipping_usd + buyee_service_fee_usd + 
                    international_shipping_usd + duty_usd + tax_usd)
        
        return LandedCost(
            item_price_jpy=package_info.item_price_jpy,
            item_price_usd=item_price_usd,
            domestic_shipping_jpy=package_info.domestic_shipping_jpy,
            domestic_shipping_usd=domestic_shipping_usd,
            buyee_service_fee_jpy=package_info.buyee_service_fee_jpy,
            buyee_service_fee_usd=buyee_service_fee_usd,
            international_shipping_jpy=selected_shipping.cost_jpy,
            international_shipping_usd=international_shipping_usd,
            us_customs_duty_usd=duty_usd,
            us_customs_tax_usd=tax_usd,
            total_jpy=total_jpy,
            total_usd=total_usd,
            exchange_rate=self.exchange_rate,
            shipping_method=shipping_method
        )
    
    def print_landed_cost(self, landed_cost: LandedCost, package_info: Optional[PackageInfo] = None):
        """Print formatted landed cost breakdown"""
        print("\n" + "="*60)
        print("LANDED COST BREAKDOWN")
        print("="*60)
        
        if package_info and package_info.item_name:
            print(f"\nItem: {package_info.item_name}")
        
        print(f"\nExchange Rate: 1 JPY = ${landed_cost.exchange_rate:.6f} USD")
        print(f"\nCost Breakdown:")
        print(f"  Item Price:              {landed_cost.item_price_jpy:,.0f} JPY (${landed_cost.item_price_usd:,.2f} USD)")
        print(f"  Domestic Shipping:       {landed_cost.domestic_shipping_jpy:,.0f} JPY (${landed_cost.domestic_shipping_usd:,.2f} USD)")
        print(f"  Buyee Service Fee:       {landed_cost.buyee_service_fee_jpy:,.0f} JPY (${landed_cost.buyee_service_fee_usd:,.2f} USD)")
        print(f"  International Shipping ({landed_cost.shipping_method}): {landed_cost.international_shipping_jpy:,.0f} JPY (${landed_cost.international_shipping_usd:,.2f} USD)")
        print(f"  US Customs Duty (15%):    ${landed_cost.us_customs_duty_usd:,.2f} USD")
        print(f"  US Customs Processing:    ${landed_cost.us_customs_tax_usd:,.2f} USD")
        print(f"\n{'─'*60}")
        print(f"  TOTAL LANDED COST:        {landed_cost.total_jpy:,.0f} JPY (${landed_cost.total_usd:,.2f} USD)")
        print("="*60 + "\n")


def main():
    """Main function for command-line usage"""
    import sys
    
    # Default destination
    destination_address = "19 Wildwood Hts, West Sand Lake, NY"
    destination_zip = "12196"
    
    if len(sys.argv) < 2:
        print("Usage: python buyee_landed_cost.py <buyee_link> [shipping_method]")
        print("\nSupports:")
        print("  - Buyee item/product links (e.g., https://buyee.jp/item/...)")
        print("  - Rakuma items (e.g., https://buyee.jp/rakuma/item/...)")
        print("  - Mercari items via Buyee")
        print("  - Yahoo Auctions via Buyee")
        print("  - Buyee package links (e.g., https://buyee.jp/package/...)")
        print("\nShipping methods: EMS, FedEx Air, FedEx Economy, DHL, Buyee Air Delivery")
        print("\nShipping methods: EMS, FedEx Air, FedEx Economy, DHL")
        print("\nExamples:")
        print("  python buyee_landed_cost.py https://buyee.jp/item/detail/123456 EMS")
        print("  python buyee_landed_cost.py https://buyee.jp/package/123456 EMS")
        sys.exit(1)
    
    buyee_link = sys.argv[1]
    shipping_method = sys.argv[2] if len(sys.argv) > 2 else "EMS"
    
    calculator = BuyeeLandedCostCalculator(destination_address, destination_zip)
    
    try:
        landed_cost = calculator.calculate_landed_cost(buyee_link, shipping_method)
        calculator.print_landed_cost(landed_cost)
    except Exception as e:
        print(f"\nError calculating landed cost: {e}")
        print("\nIf automatic extraction failed, you can provide manual values:")
        print("  calculator.calculate_landed_cost(")
        print("      buyee_link,")
        print("      shipping_method='EMS',")
        print("      manual_weight_kg=1.5,")
        print("      manual_length_cm=30,")
        print("      manual_width_cm=20,")
        print("      manual_height_cm=15,")
        print("      manual_price_jpy=5000")
        print("  )")
        sys.exit(1)


if __name__ == "__main__":
    main()
