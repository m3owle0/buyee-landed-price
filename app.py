#!/usr/bin/env python3
"""
Flask web application for Buyee Landed Cost Calculator
"""

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from buyee_landed_cost import BuyeeLandedCostCalculator, LandedCost
import traceback
import os
from datetime import datetime

app = Flask(__name__)

# CORS support for GitHub Pages
from flask_cors import CORS
CORS(app)  # Allow requests from any origin (GitHub Pages)

# Database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(basedir, "buyee_calculator.db")}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Database Models
class CalculationHistory(db.Model):
    """Store calculation history"""
    __tablename__ = 'calculation_history'
    
    id = db.Column(db.Integer, primary_key=True)
    link = db.Column(db.String(500), nullable=False)
    item_name = db.Column(db.String(500))
    destination_address = db.Column(db.String(200), nullable=False)
    destination_zip = db.Column(db.String(20), nullable=False)
    shipping_method = db.Column(db.String(50), nullable=False)
    item_price_jpy = db.Column(db.Float)
    item_price_usd = db.Column(db.Float)
    domestic_shipping_jpy = db.Column(db.Float)
    domestic_shipping_usd = db.Column(db.Float)
    buyee_service_fee_jpy = db.Column(db.Float)
    buyee_service_fee_usd = db.Column(db.Float)
    international_shipping_jpy = db.Column(db.Float)
    international_shipping_usd = db.Column(db.Float)
    us_customs_duty_usd = db.Column(db.Float)
    us_customs_tax_usd = db.Column(db.Float)
    total_jpy = db.Column(db.Float)
    total_usd = db.Column(db.Float)
    exchange_rate = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'link': self.link,
            'item_name': self.item_name,
            'destination_address': self.destination_address,
            'destination_zip': self.destination_zip,
            'shipping_method': self.shipping_method,
            'item_price_jpy': self.item_price_jpy,
            'item_price_usd': self.item_price_usd,
            'domestic_shipping_jpy': self.domestic_shipping_jpy,
            'domestic_shipping_usd': self.domestic_shipping_usd,
            'buyee_service_fee_jpy': self.buyee_service_fee_jpy,
            'buyee_service_fee_usd': self.buyee_service_fee_usd,
            'international_shipping_jpy': self.international_shipping_jpy,
            'international_shipping_usd': self.international_shipping_usd,
            'us_customs_duty_usd': self.us_customs_duty_usd,
            'us_customs_tax_usd': self.us_customs_tax_usd,
            'total_jpy': self.total_jpy,
            'total_usd': self.total_usd,
            'exchange_rate': self.exchange_rate,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class SavedAddress(db.Model):
    """Store saved delivery addresses"""
    __tablename__ = 'saved_addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(200), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime, default=datetime.utcnow)
    use_count = db.Column(db.Integer, default=1)
    
    def to_dict(self):
        return {
            'id': self.id,
            'address': self.address,
            'zip_code': self.zip_code,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'use_count': self.use_count
        }

# Initialize database tables
with app.app_context():
    db.create_all()

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
        save_to_db = data.get('save_to_db', True)  # Default to saving
        
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
        
        # Save to database if requested
        if save_to_db:
            try:
                calc_history = CalculationHistory(
                    link=buyee_link,
                    item_name=item_name,
                    destination_address=destination_address,
                    destination_zip=destination_zip,
                    shipping_method=shipping_method,
                    item_price_jpy=landed_cost.item_price_jpy,
                    item_price_usd=landed_cost.item_price_usd,
                    domestic_shipping_jpy=landed_cost.domestic_shipping_jpy,
                    domestic_shipping_usd=landed_cost.domestic_shipping_usd,
                    buyee_service_fee_jpy=landed_cost.buyee_service_fee_jpy,
                    buyee_service_fee_usd=landed_cost.buyee_service_fee_usd,
                    international_shipping_jpy=landed_cost.international_shipping_jpy,
                    international_shipping_usd=landed_cost.international_shipping_usd,
                    us_customs_duty_usd=landed_cost.us_customs_duty_usd,
                    us_customs_tax_usd=landed_cost.us_customs_tax_usd,
                    total_jpy=landed_cost.total_jpy,
                    total_usd=landed_cost.total_usd,
                    exchange_rate=landed_cost.exchange_rate
                )
                db.session.add(calc_history)
                db.session.commit()
                result['history_id'] = calc_history.id
            except Exception as db_error:
                # Don't fail the request if database save fails
                print(f"Database save error: {db_error}")
        
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
                
                result_item = {
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
                }
                
                # Save to database
                try:
                    calc_history = CalculationHistory(
                        link=link,
                        item_name=package_info.item_name if package_info else "",
                        destination_address=destination_address,
                        destination_zip=destination_zip,
                        shipping_method=shipping_method,
                        item_price_jpy=landed_cost.item_price_jpy,
                        item_price_usd=landed_cost.item_price_usd,
                        domestic_shipping_jpy=landed_cost.domestic_shipping_jpy,
                        domestic_shipping_usd=landed_cost.domestic_shipping_usd,
                        buyee_service_fee_jpy=landed_cost.buyee_service_fee_jpy,
                        buyee_service_fee_usd=landed_cost.buyee_service_fee_usd,
                        international_shipping_jpy=landed_cost.international_shipping_jpy,
                        international_shipping_usd=landed_cost.international_shipping_usd,
                        us_customs_duty_usd=landed_cost.us_customs_duty_usd,
                        us_customs_tax_usd=landed_cost.us_customs_tax_usd,
                        total_jpy=landed_cost.total_jpy,
                        total_usd=landed_cost.total_usd,
                        exchange_rate=exchange_rate
                    )
                    db.session.add(calc_history)
                    result_item['history_id'] = calc_history.id
                except Exception as db_error:
                    print(f"Database save error: {db_error}")
                
                results.append(result_item)
            except Exception as e:
                results.append({
                    'success': False,
                    'link': link,
                    'error': str(e)
                })
        
        # Commit all database saves
        try:
            db.session.commit()
        except Exception as db_error:
            print(f"Database commit error: {db_error}")
            db.session.rollback()
        
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

# Database API Endpoints

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get calculation history"""
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        history = CalculationHistory.query.order_by(CalculationHistory.created_at.desc()).limit(limit).offset(offset).all()
        
        return jsonify({
            'success': True,
            'history': [h.to_dict() for h in history],
            'total': CalculationHistory.query.count()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/history/<int:history_id>', methods=['GET'])
def get_history_item(history_id):
    """Get a specific calculation history item"""
    try:
        item = CalculationHistory.query.get_or_404(history_id)
        return jsonify({
            'success': True,
            'item': item.to_dict()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/addresses', methods=['GET'])
def get_addresses():
    """Get saved addresses"""
    try:
        addresses = SavedAddress.query.order_by(SavedAddress.last_used.desc()).all()
        return jsonify({
            'success': True,
            'addresses': [a.to_dict() for a in addresses]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/addresses', methods=['POST'])
def save_address():
    """Save a new address"""
    try:
        data = request.json
        address = data.get('address', '').strip()
        zip_code = data.get('zip_code', '').strip()
        name = data.get('name', '').strip()
        
        if not address or not zip_code:
            return jsonify({'error': 'Address and ZIP code are required'}), 400
        
        # Check if address already exists
        existing = SavedAddress.query.filter_by(
            address=address,
            zip_code=zip_code
        ).first()
        
        if existing:
            # Update last used and increment count
            existing.last_used = datetime.utcnow()
            existing.use_count += 1
            if name:
                existing.name = name
            db.session.commit()
            return jsonify({
                'success': True,
                'address': existing.to_dict(),
                'message': 'Address updated'
            })
        else:
            # Create new address
            new_address = SavedAddress(
                address=address,
                zip_code=zip_code,
                name=name
            )
            db.session.add(new_address)
            db.session.commit()
            return jsonify({
                'success': True,
                'address': new_address.to_dict(),
                'message': 'Address saved'
            })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/addresses/<int:address_id>', methods=['DELETE'])
def delete_address(address_id):
    """Delete a saved address"""
    try:
        address = SavedAddress.query.get_or_404(address_id)
        db.session.delete(address)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Address deleted'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistics about calculations"""
    try:
        total_calculations = CalculationHistory.query.count()
        total_saved = SavedAddress.query.count()
        
        # Get total spent (sum of all calculations)
        total_spent = db.session.query(db.func.sum(CalculationHistory.total_usd)).scalar() or 0
        
        # Get most used shipping method
        shipping_stats = db.session.query(
            CalculationHistory.shipping_method,
            db.func.count(CalculationHistory.id)
        ).group_by(CalculationHistory.shipping_method).all()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_calculations': total_calculations,
                'total_saved_addresses': total_saved,
                'total_spent_usd': round(total_spent, 2),
                'shipping_methods': {method: count for method, count in shipping_stats}
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    import os
    # Production: use environment variables, development: use defaults
    debug_mode = os.environ.get('FLASK_DEBUG', 'False') == 'True'
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(debug=debug_mode, host=host, port=port)
