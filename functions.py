from models import db, User, Group, Transaction, GroupInvitation, GroupMembership
from datetime import datetime, timezone

def init_db(app):
    with app.app_context():
        db.drop_all()
        db.create_all()
        
        admin = User(
            username='admin',
            email='admin@cotismart.com',
            password='Adelphedoua.',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()

        simple_user = User(
            username='Arelle Oviane',
            email='oviane74@gmail.com',
            password='Arelledoua',
            role='user'
        )
        db.session.add(simple_user)
        db.session.commit()

        simple_user2 = User(
            username='Adelphe Doua',
            email='adelphedoua04@gmail.com',
            password='Adelphedoua.',
            role='user'
        )
        db.session.add(simple_user2)
        db.session.commit()

def get_pending_invitations_count(user_id):
    return GroupInvitation.query.filter_by(
        user_id=user_id,
        status='pending'
    ).count()

def get_member_contributions(group_id):
    contributions = db.session.query(
        User.username,
        db.func.sum(Transaction.amount).label('total_contribution')
    ).join(Transaction, User.id == Transaction.member_id)\
     .filter(Transaction.group_id == group_id, Transaction.type == 'deposit')\
     .group_by(User.username)\
     .all()
    return contributions

def calculate_periods(start_date, frequency):
    now = datetime.now(timezone.utc).date()
    if now < start_date:
        return 0

    if frequency == 'daily':
        return (now - start_date).days
    elif frequency == 'weekly':
        return (now - start_date).days // 7
    elif frequency == 'monthly':
        return (now.year - start_date.year) * 12 + now.month - start_date.month
    return 0

def calculate_total_due(periods, contribution_amount):
    return periods * contribution_amount