#!/usr/bin/env python3
"""
Flask web application for Buyee Landed Cost Calculator
"""

from flask import Flask, render_template, request, jsonify
from buyee_landed_cost import BuyeeLandedCostCalculator, LandedCost
import traceback

app = Flask(__name__)

# CORS support for GitHub Pages
from flask_cors import CORS
CORS(app)  # Allow requests from any origin (GitHub Pages)

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/calculate', methods=['POST'])
def calculate():
    """Calculate landed cost for a single link"""
    try:
        data = request.json
        buyee_link = data.get('link', '').strip()
        shipping_method = data.get('shipping_method', 'EMS')
        destination_address = data.get('destination_address', '')
        destination_zip = data.get('destination_zip', '')
        
        if not buyee_link:
            return jsonify({'error': 'No link provided'}), 400
        
        if not destination_address or not destination_zip:
            return jsonify({'error': 'Destination address and ZIP code are required'}), 400
        
        calculator = BuyeeLandedCostCalculator(destination_address, destination_zip)
        
        # Calculate landed cost
        landed_cost = calculator.calculate_landed_cost(buyee_link, shipping_method)
        
        # Try to get package info for item name
        try:
            is_item = calculator.is_item_link(buyee_link)
            if is_item:
                package_info = calculator.extract_item_info(buyee_link)
            else:
                package_info = calculator.extract_package_info(buyee_link)
            item_name = package_info.item_name if package_info else ""
        except:
            item_name = ""
        
        result = {
            'success': True,
            'link': buyee_link,
            'item_name': item_name,
            'shipping_method': shipping_method,
            'exchange_rate': landed_cost.exchange_rate,
            'item_price_jpy': round(landed_cost.item_price_jpy, 0),
            'item_price_usd': round(landed_cost.item_price_usd, 2),
            'domestic_shipping_jpy': round(landed_cost.domestic_shipping_jpy, 0),
            'domestic_shipping_usd': round(landed_cost.domestic_shipping_usd, 2),
            'buyee_service_fee_jpy': round(landed_cost.buyee_service_fee_jpy, 0),
            'buyee_service_fee_usd': round(landed_cost.buyee_service_fee_usd, 2),
            'international_shipping_jpy': round(landed_cost.international_shipping_jpy, 0),
            'international_shipping_usd': round(landed_cost.international_shipping_usd, 2),
            'us_customs_duty_usd': round(landed_cost.us_customs_duty_usd, 2),
            'us_customs_tax_usd': round(landed_cost.us_customs_tax_usd, 2),
            'total_jpy': round(landed_cost.total_jpy, 0),
            'total_usd': round(landed_cost.total_usd, 2)
        }
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/calculate_batch', methods=['POST'])
def calculate_batch():
    """Calculate landed costs for multiple links"""
    try:
        data = request.json
        links = data.get('links', [])
        shipping_method = data.get('shipping_method', 'EMS')
        consolidated = data.get('consolidated', False)
        
        # Get destination from request (no hardcoded address)
        destination_address = data.get('destination_address', '')
        destination_zip = data.get('destination_zip', '')
        
        if not destination_address or not destination_zip:
            return jsonify({'error': 'Destination address and ZIP code are required'}), 400
        
        if not links:
            return jsonify({'error': 'No links provided'}), 400
        
        results = []
        calculator = BuyeeLandedCostCalculator(destination_address, destination_zip)
        package_infos = []
        
        # First pass: extract all package info
        exchange_rate = calculator.get_exchange_rate()
        
        for link in links:
            link = link.strip()
            if not link:
                continue
                
            try:
                is_item = calculator.is_item_link(link)
                if is_item:
                    package_info = calculator.extract_item_info(link)
                else:
                    package_info = calculator.extract_package_info(link)
                
                # Calculate individual costs for display (always calculate individual for comparison)
                landed_cost = calculator.calculate_landed_cost(link, shipping_method)
                
                package_infos.append({
                    'info': package_info,
                    'link': link,
                    'landed_cost': landed_cost
                })
                
                results.append({
                    'success': True,
                    'link': link,
                    'item_name': package_info.item_name if package_info else "",
                    'shipping_method': shipping_method,
                    'exchange_rate': exchange_rate,
                    'item_price_jpy': round(landed_cost.item_price_jpy, 0),
                    'item_price_usd': round(landed_cost.item_price_usd, 2),
                    'domestic_shipping_jpy': round(landed_cost.domestic_shipping_jpy, 0),
                    'domestic_shipping_usd': round(landed_cost.domestic_shipping_usd, 2),
                    'buyee_service_fee_jpy': round(landed_cost.buyee_service_fee_jpy, 0),
                    'buyee_service_fee_usd': round(landed_cost.buyee_service_fee_usd, 2),
                    'international_shipping_jpy': round(landed_cost.international_shipping_jpy, 0),
                    'international_shipping_usd': round(landed_cost.international_shipping_usd, 2),
                    'us_customs_duty_usd': round(landed_cost.us_customs_duty_usd, 2),
                    'us_customs_tax_usd': round(landed_cost.us_customs_tax_usd, 2),
                    'total_jpy': round(landed_cost.total_jpy, 0),
                    'total_usd': round(landed_cost.total_usd, 2)
                })
            except Exception as e:
                results.append({
                    'success': False,
                    'link': link,
                    'error': str(e)
                })
        
        # If consolidated mode, calculate combined shipping
        if consolidated and len([p for p in package_infos if p.get('info')]) > 1:
            # Calculate consolidated dimensions and weight
            package_info_list = [p['info'] for p in package_infos if p.get('info')]
            total_weight, max_length, max_width, total_height = calculator.calculate_consolidated_shipping(
                package_info_list, shipping_method
            )
            
            # Calculate consolidated international shipping
            shipping_options = calculator.estimate_international_shipping(
                total_weight, max_length, max_width, total_height
            )
            consolidated_shipping = shipping_options.get(shipping_method)
            if not consolidated_shipping:
                consolidated_shipping = shipping_options.get('EMS')
            
            # Consolidation fee (typically 500 JPY per package after first)
            consolidation_fee_jpy = 500 * (len(package_info_list) - 1)
            consolidation_fee_usd = consolidation_fee_jpy * exchange_rate
            
            # Sum all item prices, domestic shipping, and service fees
            total_item_price_usd = sum(p['landed_cost'].item_price_usd for p in package_infos if p.get('landed_cost'))
            total_domestic_shipping_usd = sum(p['landed_cost'].domestic_shipping_usd for p in package_infos if p.get('landed_cost'))
            total_buyee_service_fee_usd = sum(p['landed_cost'].buyee_service_fee_usd for p in package_infos if p.get('landed_cost'))
            
            # Single international shipping for consolidated package
            consolidated_international_shipping_usd = consolidated_shipping.cost_jpy * exchange_rate
            
            # Combined declared value for customs
            total_declared_value_usd = total_item_price_usd
            duty_usd, tax_usd = calculator.calculate_us_customs(total_declared_value_usd)
            
            # Calculate consolidated total
            consolidated_total = (
                total_item_price_usd +
                total_domestic_shipping_usd +
                total_buyee_service_fee_usd +
                consolidation_fee_usd +
                consolidated_international_shipping_usd +
                duty_usd +
                tax_usd
            )
            
            # Calculate individual totals for comparison
            individual_total = sum(r['total_usd'] for r in results if r.get('success'))
            savings = individual_total - consolidated_total
            
            return jsonify({
                'success': True,
                'results': results,
                'consolidated': True,
                'consolidated_total': round(consolidated_total, 2) if consolidated_total else 0.0,
                'individual_total': round(individual_total, 2) if individual_total else 0.0,
                'savings': round(savings, 2) if savings else 0.0,
                'consolidation_fee_usd': round(consolidation_fee_usd, 2) if consolidation_fee_usd else 0.0,
                'consolidated_shipping_usd': round(consolidated_international_shipping_usd, 2) if consolidated_international_shipping_usd else 0.0,
                'total_all': round(consolidated_total, 2) if consolidated_total else 0.0,
                'count': len(results),
                'success_count': sum(1 for r in results if r.get('success'))
            })
        else:
            # Calculate totals (individual shipping)
            total_all = sum(r['total_usd'] for r in results if r.get('success'))
            
            return jsonify({
                'success': True,
                'results': results,
                'consolidated': False,
                'total_all': round(total_all, 2),
                'count': len(results),
                'success_count': sum(1 for r in results if r.get('success'))
            })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

if __name__ == '__main__':
    import os
    # Production: use environment variables, development: use defaults
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(debug=debug_mode, host=host, port=port)
