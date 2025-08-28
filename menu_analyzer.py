#!/usr/bin/env python3
"""
Fixed Menu Analyzer with proper Penn State form handling
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import os
import time


class MenuAnalyzer:
    def __init__(self, gemini_api_key: str = None, exclude_beef=False, exclude_pork=False,
                 vegetarian=False, debug=False):
        self.base_url = "https://www.absecom.psu.edu/menus/user-pages/daily-menu.cfm"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.debug = debug
        self.exclude_beef = exclude_beef
        self.exclude_pork = exclude_pork
        self.vegetarian = vegetarian
        gemini_api_key='AIzaSyC3k6AqP0dgg_LvOdKsNAorKWe9Xqf_bl0'

        # Gemini API setup
        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        if self.gemini_api_key:
            self.gemini_url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
                f"?key={self.gemini_api_key}"
            )
        elif self.debug:
            print("No Gemini API key provided. Using local analysis only.")

    def fetch_initial_page(self) -> BeautifulSoup:
        """Fetch the initial menu page to get form data"""
        try:
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            if self.debug:
                print(f"Error fetching initial page: {e}")
            return None

    def get_form_options(self, soup: BeautifulSoup) -> Dict[str, Dict[str, str]]:
        """Extract all form options for campus, meal, and date selection"""
        options = {
            'campus': {},
            'meal': {},
            'date': {}
        }
        
        # Find campus options
        campus_select = soup.find('select', {'name': 'selCampus'})
        if campus_select:
            for option in campus_select.find_all('option'):
                value = option.get('value', '')
                text = option.get_text(strip=True)
                if value and text:
                    options['campus'][text] = value
                    if self.debug and 'altoona' in text.lower():
                        print(f"Found Altoona campus option: '{text}' -> '{value}'")

        # Find meal options
        meal_select = soup.find('select', {'name': 'selMeal'})
        if meal_select:
            for option in meal_select.find_all('option'):
                value = option.get('value', '')
                text = option.get_text(strip=True)
                if value and text:
                    options['meal'][text] = value
                    if self.debug:
                        print(f"Found meal option: '{text}' -> '{value}'")

        # Find date options
        date_select = soup.find('select', {'name': 'selMenuDate'})
        if date_select:
            for option in date_select.find_all('option'):
                value = option.get('value', '')
                text = option.get_text(strip=True)
                if value and text:
                    options['date'][text] = value

        return options

    def get_altoona_campus_value(self, form_options: Dict[str, Dict[str, str]]) -> Optional[str]:
        """Find the correct value for Altoona campus"""
        campus_options = form_options.get('campus', {})
        
        # Look for Altoona in various formats
        altoona_patterns = ['altoona', 'port sky', 'port sky cafe']
        
        for campus_name, campus_value in campus_options.items():
            campus_lower = campus_name.lower()
            if any(pattern in campus_lower for pattern in altoona_patterns):
                if self.debug:
                    print(f"Selected Altoona campus: '{campus_name}' (value: {campus_value})")
                return campus_value
        
        if self.debug:
            print("Available campus options:")
            for name, value in campus_options.items():
                print(f"  - '{name}' -> '{value}'")
            print("Could not find Altoona campus option!")
        
        return None

    def fetch_specific_meal(self, campus_value: str, meal_value: str, date_value: str = "") -> List[str]:
        """Fetch menu for specific campus, meal, and date"""
        try:
            form_data = {
                'selCampus': campus_value,
                'selMeal': meal_value,
                'selMenuDate': date_value  # Empty string for today's date
            }
            
            if self.debug:
                print(f"Submitting form data: {form_data}")
            
            response = self.session.post(self.base_url, data=form_data, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Save debug HTML for this specific meal
            if self.debug:
                meal_name = meal_value.replace(' ', '_').lower()
                filename = f"debug_{meal_name}_altoona.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(soup.prettify())
                print(f"Saved {meal_name} HTML to {filename}")
            
            return self.extract_food_items_from_response(soup)
            
        except Exception as e:
            if self.debug:
                print(f"Error fetching meal {meal_value}: {e}")
            return []

    def extract_food_items_from_response(self, soup: BeautifulSoup) -> List[str]:
        """Extract food items from the menu response page"""
        food_items = []
        
        # Method 1: Look for menu item containers
        menu_containers = soup.find_all(['div', 'td', 'span'], 
                                       class_=re.compile(r'menu|item|food', re.IGNORECASE))
        
        for container in menu_containers:
            text = container.get_text(strip=True)
            if self.looks_like_food_item(text):
                food_items.append(text)
        
        # Method 2: Look for specific patterns in table cells
        table_cells = soup.find_all('td')
        for cell in table_cells:
            text = cell.get_text(strip=True)
            if self.looks_like_food_item(text):
                food_items.append(text)
        
        # Method 3: Look for list items
        list_items = soup.find_all('li')
        for item in list_items:
            text = item.get_text(strip=True)
            if self.looks_like_food_item(text):
                food_items.append(text)
        
        # Method 4: Look for any text that might be food items
        all_text_elements = soup.find_all(['span', 'div', 'p', 'strong', 'b'])
        for element in all_text_elements:
            text = element.get_text(strip=True)
            if self.looks_like_food_item(text) and len(text.split()) <= 6:
                food_items.append(text)
        
        # Clean up and deduplicate
        food_items = [item for item in food_items if len(item.strip()) > 2]
        food_items = list(set(food_items))  # Remove duplicates
        
        # Filter out obvious non-food items
        food_items = [item for item in food_items if not self.is_navigation_or_ui_text(item)]
        
        if self.debug:
            print(f"Extracted {len(food_items)} food items:")
            for item in food_items[:10]:  # Show first 10
                print(f"  - {item}")
            if len(food_items) > 10:
                print(f"  ... and {len(food_items) - 10} more")
        
        return food_items

    def looks_like_food_item(self, text: str) -> bool:
        """Enhanced food item detection"""
        if not text or len(text.strip()) < 3:
            return False
            
        text = text.strip()
        text_lower = text.lower()
        
        # Skip if too long (likely descriptions)
        if len(text) > 100:
            return False
        
        # Skip obvious UI/navigation text
        ui_terms = ['click', 'select', 'menu', 'page', 'home', 'login', 'search',
                   'view', 'print', 'back', 'next', 'submit', 'cancel', 'choose',
                   'options', 'settings', 'help', 'contact', 'about']
        if any(term in text_lower for term in ui_terms):
            return False
        
        # Skip if mostly numbers or special characters
        alpha_ratio = sum(c.isalpha() for c in text) / len(text)
        if alpha_ratio < 0.5:
            return False
        
        # Strong food indicators
        strong_food_words = [
            'chicken', 'beef', 'pork', 'fish', 'turkey', 'salmon', 'tuna',
            'burger', 'pizza', 'pasta', 'salad', 'sandwich', 'soup', 'steak',
            'rice', 'beans', 'vegetables', 'fruit', 'cheese', 'bread',
            'grilled', 'baked', 'fried', 'roasted', 'steamed', 'sautéed'
        ]
        
        if any(word in text_lower for word in strong_food_words):
            return True
        
        # Moderate food indicators
        moderate_food_words = [
            'bowl', 'plate', 'wrap', 'roll', 'cake', 'cookie', 'pie',
            'sauce', 'dressing', 'seasoned', 'spiced', 'fresh', 'hot'
        ]
        
        moderate_matches = sum(1 for word in moderate_food_words if word in text_lower)
        
        # If it has moderate indicators and looks like a reasonable food name
        if moderate_matches > 0 and 2 <= len(text.split()) <= 8:
            return True
        
        # If it's a short phrase without obvious non-food indicators
        if 2 <= len(text.split()) <= 6 and not any(char in text for char in ['@', 'http', '.com', '()', '[]']):
            # Check if it contains at least one word that could be food-related
            words = text_lower.split()
            food_like_words = [
                'bowl', 'cup', 'plate', 'special', 'daily', 'fresh', 'hot', 'cold',
                'classic', 'traditional', 'homemade', 'style', 'with', 'and'
            ]
            if any(word in food_like_words for word in words):
                return True
        
        return False

    def is_navigation_or_ui_text(self, text: str) -> bool:
        """Check if text is likely navigation or UI text"""
        text_lower = text.lower().strip()
        
        nav_phrases = [
            'view menu', 'select date', 'choose location', 'dining options',
            'meal plans', 'nutrition info', 'allergen info', 'hours',
            'locations', 'contact us', 'feedback', 'terms', 'privacy'
        ]
        
        return any(phrase in text_lower for phrase in nav_phrases)

    def run_analysis(self) -> Dict[str, List[Tuple[str, int, str]]]:
        """Main analysis with proper form handling"""
        if self.debug:
            print("Fetching initial page to get form options...")
        
        soup = self.fetch_initial_page()
        if not soup:
            if self.debug:
                print("Could not fetch initial page, using fallback data")
            return self.get_fallback_data()
        
        # Get form options
        form_options = self.get_form_options(soup)
        
        # Find Altoona campus value
        altoona_value = self.get_altoona_campus_value(form_options)
        if not altoona_value:
            if self.debug:
                print("Could not find Altoona campus, using fallback data")
            return self.get_fallback_data()
        
        # Get meal options
        meal_options = form_options.get('meal', {})
        if not meal_options:
            if self.debug:
                print("No meal options found, using fallback data")
            return self.get_fallback_data()
        
        # Fetch each meal separately
        results = {}
        meal_mapping = {
            'Breakfast': ['breakfast', 'morning'],
            'Lunch': ['lunch', 'midday'],
            'Dinner': ['dinner', 'evening', 'supper']
        }
        
        for target_meal in ['Breakfast', 'Lunch', 'Dinner']:
            meal_value = None
            
            # Find the correct meal value
            for meal_name, meal_val in meal_options.items():
                meal_name_lower = meal_name.lower()
                if any(keyword in meal_name_lower for keyword in meal_mapping[target_meal]):
                    meal_value = meal_val
                    break
            
            if meal_value:
                if self.debug:
                    print(f"Fetching {target_meal} menu...")
                
                food_items = self.fetch_specific_meal(altoona_value, meal_value)
                
                if food_items:
                    if self.debug:
                        print(f"Found {len(food_items)} items for {target_meal}")
                    
                    analyzed_items = self.analyze_food_with_gemini(food_items)
                    analyzed_items.sort(key=lambda x: x[1], reverse=True)
                    results[target_meal] = analyzed_items
                else:
                    if self.debug:
                        print(f"No food items found for {target_meal}")
            else:
                if self.debug:
                    print(f"Could not find meal option for {target_meal}")
        
        return results if results else self.get_fallback_data()

    def get_fallback_data(self) -> Dict[str, List[Tuple[str, int, str]]]:
        """Fallback data if website scraping fails"""
        fallback_meals = {
            "Breakfast": ["Scrambled Eggs", "Turkey Sausage", "Oatmeal", "Fresh Fruit", "Yogurt"],
            "Lunch": ["Grilled Chicken Salad", "Turkey Club Sandwich", "Vegetable Soup", "Quinoa Bowl"],
            "Dinner": ["Baked Salmon", "Beef Stir-Fry", "Grilled Chicken Breast", "Pasta Primavera"]
        }
        
        results = {}
        for meal_name, food_items in fallback_meals.items():
            analyzed_items = self.analyze_food_health_local(food_items)
            analyzed_items.sort(key=lambda x: x[1], reverse=True)
            results[meal_name] = analyzed_items
        
        return results

    # Include your existing analysis methods here...
    def analyze_food_with_gemini(self, food_items: List[str]) -> List[Tuple[str, int, str]]:
        if not self.gemini_api_key:
            return self.analyze_food_health_local(food_items)

        try:
            batch_size = 10
            all_results = []
            for i in range(0, len(food_items), batch_size):
                batch = food_items[i:i + batch_size]
                batch_results = self._analyze_batch_with_gemini(batch)
                all_results.extend(batch_results)
                time.sleep(1)
            return all_results
        except Exception as e:
            if self.debug:
                print(f"Gemini analysis failed: {e}")
            return self.analyze_food_health_local(food_items)

    def _analyze_batch_with_gemini(self, food_batch: List[str]) -> List[Tuple[str, int, str]]:
        food_list = "\n".join([f"- {item}" for item in food_batch])

        exclusions = []
        if self.exclude_beef:
            exclusions.append("Do not recommend beef items.")
        if self.exclude_pork:
            exclusions.append("Do not recommend pork items.")
        if self.vegetarian:
            exclusions.append("Only recommend vegetarian options.")
        restrictions_text = "\n".join(exclusions) if exclusions else "No dietary restrictions."

        prompt = f"""
        Analyze these dining hall foods for PROTEIN content and healthiness.
        {restrictions_text}

        Foods: {food_list}

        Respond in JSON format:
        {{
            "food_name": {{"score": 90, "reasoning": "High protein, healthy prep"}}
        }}
        """

        try:
            response = self.session.post(
                self.gemini_url,
                headers={"Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            text_response = data["candidates"][0]["content"]["parts"][0]["text"]

            # Clean and parse response
            text_response = re.sub(r"```(json)?", "", text_response, flags=re.IGNORECASE).strip()
            text_response = re.sub(r"```$", "", text_response).strip()

            parsed = json.loads(text_response)
            return [(food, int(info.get("score", 0)), info.get("reasoning", "")) 
                   for food, info in parsed.items()]
        except Exception as e:
            if self.debug:
                print(f"Failed to parse Gemini response: {e}")
            return self.analyze_food_health_local(food_batch)

    def analyze_food_health_local(self, food_items: List[str]) -> List[Tuple[str, int, str]]:
        """Enhanced local analysis with dietary restrictions"""
        health_scores = []

        protein_keywords = {
            'excellent': ['grilled chicken', 'baked fish', 'turkey breast', 'salmon', 'tuna'],
            'good': ['chicken', 'fish', 'turkey', 'beef', 'eggs', 'tofu', 'beans'],
            'moderate': ['cheese', 'nuts', 'yogurt', 'milk']
        }

        healthy_prep = {
            'excellent': ['grilled', 'baked', 'steamed', 'roasted', 'fresh'],
            'good': ['sautéed', 'stir-fry', 'broiled'],
            'poor': ['fried', 'deep-fried', 'battered', 'creamy']
        }

        for item in food_items:
            item_lower = item.lower()
            score = 50
            reasoning_parts = []

            # Apply dietary restrictions
            if self.exclude_beef and "beef" in item_lower:
                score = 0
                reasoning_parts.append("Excluded: contains beef")
            elif self.exclude_pork and "pork" in item_lower:
                score = 0
                reasoning_parts.append("Excluded: contains pork")
            elif self.vegetarian and any(meat in item_lower for meat in ["beef", "pork", "chicken", "fish", "turkey"]):
                score = 0
                reasoning_parts.append("Excluded: contains meat")
            else:
                # Protein scoring
                for level, keywords in protein_keywords.items():
                    matches = [kw for kw in keywords if kw in item_lower]
                    if matches:
                        if level == 'excellent':
                            score += 25
                            reasoning_parts.append(f"Excellent protein ({matches[0]})")
                        elif level == 'good':
                            score += 15
                            reasoning_parts.append(f"Good protein ({matches[0]})")
                        else:
                            score += 8
                        break

                # Preparation scoring
                for level, keywords in healthy_prep.items():
                    matches = [kw for kw in keywords if kw in item_lower]
                    if matches:
                        if level == 'excellent':
                            score += 15
                            reasoning_parts.append(f"Healthy prep ({matches[0]})")
                        elif level == 'good':
                            score += 8
                        elif level == 'poor':
                            score -= 20
                            reasoning_parts.append(f"Unhealthy prep ({matches[0]})")
                        break

            score = max(0, min(100, score))
            reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Standard option"
            health_scores.append((item, score, reasoning))

        return health_scores

    def print_detailed_recommendations(self, results: Dict[str, List[Tuple[str, int, str]]], top_n: int = 5):
        print("\n" + "="*90)
        print("HEALTHY HIGH-PROTEIN FOOD RECOMMENDATIONS - PENN STATE ALTOONA")
        print("="*90)

        all_items = []
        for meal_name, items in results.items():
            if items:
                print(f"\n{meal_name.upper()}:")
                print("-" * 60)
                for i, (food_item, score, reasoning) in enumerate(items[:top_n]):
                    print(f"{i+1}. {food_item}")
                    print(f"   Score: {score}/100")
                    print(f"   Analysis: {reasoning}")
                    print()
                    all_items.append((food_item, score, reasoning))

        if all_items:
            print("\n" + "="*90)
            top_items = sorted(all_items, key=lambda x: x[1], reverse=True)[:top_n]
            print("TOP RECOMMENDATIONS ACROSS ALL MEALS:")
            print("-" * 60)
            for i, (food, score, reasoning) in enumerate(top_items, 1):
                print(f"{i}. {food} (Score: {score}/100)")
                print(f"   {reasoning}")
                print()


if __name__ == "__main__":
    analyzer = MenuAnalyzer(
        gemini_api_key=os.getenv('GEMINI_API_KEY'),  # Set your API key
        exclude_beef=False,
        exclude_pork=False,
        vegetarian=False,
        debug=True
    )
    
    results = analyzer.run_analysis()
    analyzer.print_detailed_recommendations(results)