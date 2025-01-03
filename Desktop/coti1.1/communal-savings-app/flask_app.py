from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from flask_migrate import Migrate

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'
db = SQLAlchemy(app)

migrate = Migrate(app, db)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False, default='user')
    groups = db.relationship('GroupMembership', backref='user', lazy=True)

    def __init__(self, username, email, password, role='user'):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)
        self.role = role

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    members = db.relationship('GroupMembership', backref='group', lazy=True)

class GroupMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='member')

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(20), nullable=False)  # 'deposit' pour entrée, 'withdrawal' pour sortie
    group = db.relationship('Group', backref='transactions')
    member = db.relationship('User', backref='transactions')

class GroupInvitation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='invitations')
    group = db.relationship('Group', backref='invitations')

# Assurez-vous que la base de données est supprimée et recréée
def init_db():
    with app.app_context():
        db.drop_all()  # Supprime toutes les tables existantes
        db.create_all()  # Crée les nouvelles tables avec le bon schéma
        
        # Créer un utilisateur administrateur par défaut
        admin = User(
            username='admin',
            email='adelphedoua04@gmail.com',
            password='Adelphedoua.',
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        # Créer un deuxième utilisateur simple
        simple_user = User(
            username='Arelle Oviane',
            email='oviane74@gmail.com',
            password='Arelledoua',
            role='user'
        )
        db.session.add(simple_user)
        db.session.commit()

# Initialiser la base de données au démarrage
#init_db()

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/inscription', methods=['GET', 'POST'])
def inscription():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            return render_template('inscription.html', error='Les mots de passe ne correspondent pas')

        user = User.query.filter_by(email=email).first()
        if user:
            return render_template('inscription.html', error='L\'adresse e-mail est déjà prise')

        new_user = User(username, email, password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('connexion'))

    return render_template('inscription.html')

@app.route('/connexion', methods=['GET', 'POST'])
def connexion():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if not user:
            return render_template('connexion.html', error='Le nom d\'utilisateur est incorrect')

        if not user.check_password(password):
            return render_template('connexion.html', error='Le mot de passe est incorrect')

        session['user_id'] = user.id
        return redirect(url_for('acceuil'))

    return render_template('connexion.html')

@app.route('/acceuil')
def acceuil():
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    user = User.query.get(session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)

    # Récupérer les groupes auxquels l'utilisateur appartient
    user_group_ids = [membership.group_id for membership in user.groups]

    # Récupérer les transactions récentes uniquement pour les groupes de l'utilisateur
    recent_transactions = Transaction.query\
        .join(Group, Transaction.group_id == Group.id)\
        .join(User, Transaction.member_id == User.id)\
        .filter(Transaction.group_id.in_(user_group_ids))\
        .order_by(Transaction.date.desc())\
        .limit(5).all()

    # Calculer le solde total de l'utilisateur
    incoming_transactions = db.session.query(db.func.sum(Transaction.amount))\
        .filter(Transaction.member_id == user.id, Transaction.type == 'deposit').scalar() or 0

    outgoing_transactions = db.session.query(db.func.sum(Transaction.amount))\
        .filter(Transaction.member_id == user.id, Transaction.type == 'withdrawal').scalar() or 0

    # Calculer le solde en soustrayant les transactions sortantes des entrantes
    total_balance_user = incoming_transactions + outgoing_transactions

    return render_template('acceuil.html', 
                           user=user,
                           recent_transactions=recent_transactions,
                           pending_invitations_count=pending_invitations_count,
                           total_balance_user=total_balance_user)

@app.route('/deconnexion')
def deconnexion():
    session.pop('user_id', None)
    return redirect(url_for('connexion'))

@app.route('/group', methods=['GET', 'POST'])
def group():
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    user = User.query.get(session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)

    # Récupérer les groupes de l'utilisateur
    user_memberships = GroupMembership.query.filter_by(user_id=user.id).all()
    user_groups = [membership.group for membership in user_memberships]

    # Déterminer si l'utilisateur est admin de chaque groupe
    admin_status = {group.id: is_user_admin_of_group(user.id, group.id) for group in user_groups}

    # Calculer l'évolution du solde de la caisse
    balance_dates = []
    balance_values = []
    for group in user_groups:
        transactions = Transaction.query.filter_by(group_id=group.id).order_by(Transaction.date).all()
        balance = 0
        for transaction in transactions:
            balance += transaction.amount
            balance_dates.append(transaction.date.strftime('%d/%m/%Y'))
            balance_values.append(balance)

    if request.method == 'POST':
        action = request.form.get('action')
        
        if action in ['edit', 'delete']:
            group_id = request.form.get('group_id')
            group = Group.query.get_or_404(group_id)
            
            # Vérifier si l'utilisateur est admin du groupe
            membership = GroupMembership.query.filter_by(
                user_id=user.id,
                group_id=group_id,
                role='admin'
            ).first()
            
            if membership:
                if action == 'edit':
                    group_name = request.form.get('group_name')
                    group.name = group_name
                    db.session.commit()
                    flash('Groupe modifié avec succès !', 'success')
                elif action == 'delete':
                    # Supprimer d'abord les invitations
                    GroupInvitation.query.filter_by(group_id=group_id).delete()
                    # Supprimer les adhésions
                    GroupMembership.query.filter_by(group_id=group_id).delete()
                    # Supprimer les transactions
                    Transaction.query.filter_by(group_id=group_id).delete()
                    # Supprimer le groupe
                    db.session.delete(group)
                    db.session.commit()
                    flash('Groupe supprimé avec succès !', 'success')
        else:
            group_name = request.form.get('group_name')
            new_group = Group(name=group_name)
            db.session.add(new_group)
            db.session.commit()
            
            # Ajouter l'utilisateur actuel comme membre du groupe
            membership = GroupMembership(user_id=user.id, group_id=new_group.id, role='admin')
            db.session.add(membership)
            db.session.commit()
            flash('Groupe créé avec succès !', 'success')

    return render_template('group.html', 
                           groups=user_groups,
                           user=user,
                           admin_status=admin_status,
                           pending_invitations_count=pending_invitations_count,
                           balance_dates=balance_dates,
                           balance_values=balance_values)

@app.route('/transaction', methods=['GET', 'POST'])
def transaction():
    if 'user_id' not in session:
        return redirect(url_for('connexion'))
    
    user = User.query.get(session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    
    # Récupérer uniquement les groupes où l'utilisateur est admin
    admin_memberships = GroupMembership.query.filter_by(
        user_id=user.id,
        role='admin'
    ).all()
    admin_groups = [membership.group for membership in admin_memberships]
    
    if request.method == 'POST':
        group_id = request.form.get('group_id')
        member_id = request.form.get('member_id')
        amount = float(request.form.get('amount'))
        description = request.form.get('description')
        transaction_type = request.form.get('type')
        
        # Vérifier que l'utilisateur est admin du groupe
        is_admin = GroupMembership.query.filter_by(
            user_id=user.id,
            group_id=group_id,
            role='admin'
        ).first()
        
        if not is_admin:
            flash('Vous devez être administrateur pour effectuer des transactions', 'error')
            return redirect(url_for('transaction'))
        
        # Ajuster le montant selon le type de transaction
        final_amount = amount if transaction_type == 'deposit' else -amount
        
        # Gérer la date de la transaction
        use_today = request.form.get('use_today')
        if use_today:
            transaction_date = datetime.utcnow()
        else:
            transaction_date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d')
        
        new_transaction = Transaction(
            group_id=group_id,
            member_id=member_id,
            amount=final_amount,
            description=description,
            type=transaction_type,
            date=transaction_date
        )
        
        db.session.add(new_transaction)
        db.session.commit()
        
        flash('Transaction enregistrée avec succès!', 'success')
        return redirect(url_for('transaction'))

    return render_template('transaction.html',
                         groups=admin_groups,
                         user=user,
                         pending_invitations_count=pending_invitations_count)

@app.route('/balance/<int:group_id>')
def balance(group_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    user = User.query.get(session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    group = Group.query.get_or_404(group_id)
    
    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id
    ).first()
    
    if not membership:
        flash('Vous n\'avez pas accès à ce groupe', 'error')
        return redirect(url_for('group'))
    
    transactions = Transaction.query.filter_by(group_id=group_id).order_by(Transaction.date).all()
    
    # Calculer le solde total
    total_balance = sum(transaction.amount for transaction in transactions)
    
    # Préparer les données pour le graphique
    dates = []
    balances = []
    running_balance = 0
    
    for transaction in transactions:
        running_balance += transaction.amount
        dates.append(transaction.date.strftime('%d/%m/%Y'))
        balances.append(running_balance)
    
    # Si pas de transactions, ajouter un point de départ
    if not transactions:
        dates = [datetime.now().strftime('%d/%m/%Y')]
        balances = [0]

    return render_template('balance.html',
                         group=group,
                         total_balance=total_balance,
                         dates=dates,
                         balances=balances,
                         now=datetime.now(),
                         pending_invitations_count=pending_invitations_count)

@app.route('/group/<int:group_id>/members', methods=['GET', 'POST', 'DELETE'])
def manage_members(group_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))
    
    user = User.query.get(session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    group = Group.query.get_or_404(group_id)
    
    # Vérifier si l'utilisateur est admin du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id,
        role='admin'
    ).first()
    
    if not membership:
        return redirect(url_for('group'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        member_id = request.form.get('member_id')
        email = request.form.get('email')
        
        if action == 'add':
            new_member = User.query.filter_by(email=email).first()
            if new_member:
                # Vérifier si une invitation est déjà en attente
                existing_invitation = GroupInvitation.query.filter_by(
                    user_id=new_member.id,
                    group_id=group_id,
                    status='pending'
                ).first()
                
                if existing_invitation:
                    return jsonify({'success': False, 'message': 'Une invitation est déjà en attente pour cet utilisateur'})
                else:
                    # Créer une invitation
                    invitation = GroupInvitation(
                        user_id=new_member.id,
                        group_id=group_id
                    )
                    db.session.add(invitation)
                    db.session.commit()
                    return jsonify({'success': True, 'message': 'Invitation envoyée'})
            return jsonify({'success': False, 'message': 'Utilisateur non trouvé'})
            
        elif action == 'remove':
            membership_to_remove = GroupMembership.query.filter_by(
                user_id=member_id,
                group_id=group_id
            ).first()
            if membership_to_remove:
                db.session.delete(membership_to_remove)
                db.session.commit()
                return jsonify({'success': True})
            
        elif action == 'make_admin':
            membership_to_update = GroupMembership.query.filter_by(
                user_id=member_id,
                group_id=group_id
            ).first()
            if membership_to_update:
                membership_to_update.role = 'admin'
                db.session.commit()
                return jsonify({'success': True})
    
    # Récupérer tous les membres du groupe
    members = db.session.query(User, GroupMembership)\
        .join(GroupMembership)\
        .filter(GroupMembership.group_id == group_id)\
        .all()
    
    return render_template('manage_members.html',
                         group=group,
                         members=members,
                         current_user=user,
                         pending_invitations_count=pending_invitations_count)

@app.route('/invitations', methods=['GET', 'POST'])
def invitations():
    if 'user_id' not in session:
        return redirect(url_for('connexion'))
    
    user = User.query.get(session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    
    if request.method == 'POST':
        invitation_id = request.form.get('invitation_id')
        action = request.form.get('action')
        
        invitation = GroupInvitation.query.get_or_404(invitation_id)
        if invitation.user_id != user.id:
            return jsonify({'success': False, 'message': 'Invitation non autorisée'})
        
        if action == 'accept':
            # Créer l'adhésion au groupe
            membership = GroupMembership(
                user_id=user.id,
                group_id=invitation.group_id,
                role='member'
            )
            db.session.add(membership)
            invitation.status = 'accepted'
            flash('Vous avez rejoint le groupe avec succès !', 'success')
        elif action == 'reject':
            invitation.status = 'rejected'
            flash('Vous avez refusé l\'invitation', 'info')
            
        db.session.commit()
        return redirect(url_for('invitations'))
    
    pending_invitations = GroupInvitation.query.filter_by(
        user_id=user.id,
        status='pending'
    ).all()
    
    return render_template('invitations.html',
                         user=user,
                         invitations=pending_invitations,
                         pending_invitations_count=pending_invitations_count)

@app.route('/search_users')
def search_users():
    if 'user_id' not in session:
        return jsonify([])
    
    query = request.args.get('query', '')
    if len(query) < 2:  # Rechercher seulement si au moins 2 caractères
        return jsonify([])
    
    users = User.query.filter(
        User.username.ilike(f'%{query}%')  # ilike pour une recherche insensible à la casse
    ).limit(5).all()  # Limiter à 5 résultats
    
    return jsonify([{
        'id': user.id,
        'username': user.username,
        'email': user.email
    } for user in users])

@app.route('/get_invitation_count')
def get_invitation_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})
    
    count = get_pending_invitations_count(session['user_id'])
    return jsonify({'count': count})

@app.route('/get_group_members/<int:group_id>')
def get_group_members(group_id):
    if 'user_id' not in session:
        return jsonify([])
    
    members = db.session.query(User)\
        .join(GroupMembership)\
        .filter(GroupMembership.group_id == group_id)\
        .all()
    
    return jsonify([{
        'id': member.id,
        'username': member.username
    } for member in members])

@app.route('/group/<int:group_id>/details')
def group_details(group_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    user = User.query.get(session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id
    ).first()

    if not membership:
        flash('Vous n\'avez pas accès à ce groupe', 'error')
        return redirect(url_for('group'))

    # Récupérer l'historique des transactions
    transactions = Transaction.query.filter_by(group_id=group_id).order_by(Transaction.date).all()

    # Calculer l'évolution du solde de la caisse
    balance_dates = []
    balance_values = []
    balance = 0
    for transaction in transactions:
        balance += transaction.amount
        balance_dates.append(transaction.date.strftime('%d/%m/%Y'))
        balance_values.append(balance)

    # Calculer les contributions de chaque membre
    member_contributions = {}
    total_incoming = 0
    total_outgoing = 0
    for transaction in transactions:
        if transaction.type == 'deposit':
            total_incoming += transaction.amount
        elif transaction.type == 'withdrawal':
            total_outgoing += transaction.amount

        if transaction.member_id not in member_contributions:
            member_contributions[transaction.member_id] = 0
        member_contributions[transaction.member_id] += transaction.amount

    # Récupérer les utilisateurs impliqués dans les transactions
    user_ids = member_contributions.keys()
    users = {user.id: user for user in User.query.filter(User.id.in_(user_ids)).all()}

    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('group_details.html', 
                           group=group, 
                           transactions=transactions, 
                           balance_dates=balance_dates,
                           balance_values=balance_values,
                           member_contributions=member_contributions,
                           total_incoming=total_incoming,
                           total_outgoing=total_outgoing,
                           users=users,
                           pending_invitations_count=pending_invitations_count)

@app.route('/transaction/edit/<int:transaction_id>', methods=['GET', 'POST'])
def edit_transaction(transaction_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    transaction = Transaction.query.get_or_404(transaction_id)
    user = User.query.get(session['user_id'])

    # Vérifier si l'utilisateur est admin du groupe de la transaction
    is_admin = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=transaction.group_id,
        role='admin'
    ).first()

    if not is_admin:
        flash('Vous devez être administrateur pour modifier cette transaction', 'error')
        return redirect(url_for('group_transactions', group_id=transaction.group_id))

    if request.method == 'POST':
        transaction.member_id = request.form.get('member_id')
        transaction.amount = float(request.form.get('amount'))
        transaction.description = request.form.get('description')
        transaction.type = request.form.get('type')
        transaction.date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d')
        
        db.session.commit()
        flash('Transaction modifiée avec succès!', 'success')
        return redirect(url_for('group_transactions', group_id=transaction.group_id))

    members = db.session.query(User).join(GroupMembership).filter(GroupMembership.group_id == transaction.group_id).all()
    group = Group.query.get(transaction.group_id)  # Récupérer le groupe associé à la transaction
    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('edit_transaction.html', 
                           transaction=transaction, 
                           members=members, 
                           group=group,
                           pending_invitations_count=pending_invitations_count)

@app.route('/transaction/delete/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    transaction = Transaction.query.get_or_404(transaction_id)
    user = User.query.get(session['user_id'])

    # Vérifier si l'utilisateur est admin du groupe de la transaction
    is_admin = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=transaction.group_id,
        role='admin'
    ).first()

    if not is_admin:
        flash('Vous devez être administrateur pour supprimer cette transaction', 'error')
        return redirect(url_for('transaction'))

    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction supprimée avec succès!', 'success')
    return redirect(url_for('transaction'))

@app.route('/group/<int:group_id>/transactions', methods=['GET', 'POST'])
def group_transactions(group_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))
    
    user = User.query.get(session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id
    ).first()

    if not membership:
        flash('Vous n\'avez pas accès à ce groupe', 'error')
        return redirect(url_for('group'))

    # Récupérer les transactions du groupe
    transactions = Transaction.query.filter_by(group_id=group_id).order_by(Transaction.date.desc()).all()

    # Vérifier si l'utilisateur est admin du groupe
    is_admin = membership.role == 'admin'

    if request.method == 'POST' and is_admin:
        member_id = request.form.get('member_id')
        amount = float(request.form.get('amount'))
        description = request.form.get('description')
        transaction_type = request.form.get('type')
        
        # Ajuster le montant selon le type de transaction
        final_amount = amount if transaction_type == 'deposit' else -amount
        
        # Gérer la date de la transaction
        use_today = request.form.get('use_today')
        if use_today:
            transaction_date = datetime.utcnow()
        else:
            transaction_date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d')
        
        new_transaction = Transaction(
            group_id=group_id,
            member_id=member_id,
            amount=final_amount,
            description=description,
            type=transaction_type,
            date=transaction_date
        )
        
        db.session.add(new_transaction)
        db.session.commit()
        
        flash('Transaction enregistrée avec succès!', 'success')
        return redirect(url_for('group_transactions', group_id=group_id))

    members = db.session.query(User).join(GroupMembership).filter(GroupMembership.group_id == group_id).all()
    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('transaction.html',
                           group=group,
                           transactions=transactions,
                           members=members,
                           user=user,
                           is_admin=is_admin,
                           pending_invitations_count=pending_invitations_count)

@app.route('/group/<int:group_id>/add_transaction', methods=['GET', 'POST'])
def add_transaction(group_id):
    if 'user_id' not in session:
        return redirect(url_for('connexion'))
    
    user = User.query.get(session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est admin du groupe
    is_admin = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id,
        role='admin'
    ).first()

    if not is_admin:
        flash('Vous devez être administrateur pour ajouter des transactions', 'error')
        return redirect(url_for('group_transactions', group_id=group_id))

    if request.method == 'POST':
        member_id = request.form.get('member_id')
        amount = float(request.form.get('amount'))
        description = request.form.get('description')
        transaction_type = request.form.get('type')
        
        # Ajuster le montant selon le type de transaction
        final_amount = amount if transaction_type == 'deposit' else -amount
        
        # Gérer la date de la transaction
        use_today = request.form.get('use_today')
        if use_today:
            transaction_date = datetime.utcnow()
        else:
            transaction_date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d')
        
        new_transaction = Transaction(
            group_id=group_id,
            member_id=member_id,
            amount=final_amount,
            description=description,
            type=transaction_type,
            date=transaction_date
        )
        
        db.session.add(new_transaction)
        db.session.commit()
        
        flash('Transaction ajoutée avec succès!', 'success')
        return redirect(url_for('group_transactions', group_id=group_id))

    members = db.session.query(User).join(GroupMembership).filter(GroupMembership.group_id == group_id).all()
    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('add_transaction.html',
                           group=group,
                           members=members,
                           user=user,
                           pending_invitations_count=pending_invitations_count)

def is_user_admin_of_group(user_id, group_id):
    membership = GroupMembership.query.filter_by(
        user_id=user_id,
        group_id=group_id,
        role='admin'
    ).first()
    return membership is not None

@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    if 'user_id' not in session:
        return redirect(url_for('connexion'))

    user = User.query.get(session['user_id'])
    if user.role != 'admin':
        flash('Accès refusé : vous devez être administrateur pour accéder à cette page.', 'error')
        return redirect(url_for('acceuil'))

    # Récupérer les informations nécessaires
    total_users = User.query.count()
    total_groups = Group.query.count()
    pending_invitations_count = get_pending_invitations_count(user.id)

    if request.method == 'POST':
        new_admin_email = request.form.get('new_admin_email')
        new_admin = User.query.filter_by(email=new_admin_email).first()
        if new_admin:
            new_admin.role = 'admin'
            db.session.commit()
            flash(f'{new_admin.username} a été promu administrateur.', 'success')
        else:
            flash('Utilisateur non trouvé.', 'error')

    return render_template('admin_panel.html', 
                           total_users=total_users, 
                           total_groups=total_groups,
                           pending_invitations_count=pending_invitations_count)

if __name__ == '__main__':
    app.run(debug=True)