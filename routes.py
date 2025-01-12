from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from models import db, User, Group, Transaction, GroupMembership, GroupInvitation
from functions import get_pending_invitations_count, calculate_periods, calculate_total_due
from datetime import datetime, timezone, timedelta

app_routes = Blueprint('app_routes', __name__)

@app_routes.route('/')
def index():
    return render_template('index.html')

@app_routes.route('/inscription', methods=['GET', 'POST'])
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

        return redirect(url_for('app_routes.connexion'))

    return render_template('inscription.html')

@app_routes.route('/connexion', methods=['GET', 'POST'])
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
        return redirect(url_for('app_routes.acceuil'))

    return render_template('connexion.html')

@app_routes.route('/acceuil')
def acceuil():
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    user = db.session.get(User, session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)

    user_groups = [membership.group for membership in user.groups]

    recent_transactions = Transaction.query\
        .join(Group, Transaction.group_id == Group.id)\
        .join(User, Transaction.member_id == User.id)\
        .filter(Transaction.group_id.in_([group.id for group in user_groups]))\
        .order_by(Transaction.date.desc())\
        .all()

    incoming_transactions = db.session.query(db.func.sum(Transaction.amount))\
        .filter(Transaction.member_id == user.id, Transaction.type == 'deposit').scalar() or 0

    outgoing_transactions = db.session.query(db.func.sum(Transaction.amount))\
        .filter(Transaction.member_id == user.id, Transaction.type == 'withdrawal').scalar() or 0

    total_balance_user = incoming_transactions + outgoing_transactions

    group_contributions = {}
    for group in user_groups:
        start_date = group.start_date
        frequency = group.contribution_frequency

        periods = calculate_periods(start_date, frequency)
        total_due = calculate_total_due(periods, group.contribution_amount)

        paid = db.session.query(db.func.sum(Transaction.amount))\
            .filter(Transaction.member_id == user.id, Transaction.group_id == group.id, Transaction.type == 'deposit').scalar() or 0

        remaining = max(total_due - paid, 0)
        group_contributions[group.id] = {
            'remaining': remaining,
            'total_due': total_due
        }

    return render_template('acceuil.html', 
                           user=user,
                           user_groups=user_groups,
                           recent_transactions=recent_transactions,
                           pending_invitations_count=pending_invitations_count,
                           total_balance_user=total_balance_user,
                           group_contributions=group_contributions)

@app_routes.route('/deconnexion')
def deconnexion():
    session.pop('user_id', None)
    return redirect(url_for('app_routes.connexion'))

@app_routes.route('/group', methods=['GET', 'POST'])
def group():
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    user = db.session.get(User, session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)

    if request.method == 'POST':
        if request.form.get('action') == 'delete':
            group_id = request.form.get('group_id')
            group_to_delete = Group.query.get(group_id)
            if group_to_delete:
                Transaction.query.filter_by(group_id=group_id).delete()
                GroupMembership.query.filter_by(group_id=group_id).delete()
                GroupInvitation.query.filter_by(group_id=group_id).delete()
                db.session.delete(group_to_delete)
                db.session.commit()
                flash('Groupe supprimé avec succès !', 'success')
            else:
                flash('Groupe non trouvé.', 'error')
            return redirect(url_for('app_routes.group'))

        group_name = request.form.get('group_name')
        contribution_frequency = request.form.get('contribution_frequency')
        start_date_str = request.form.get('start_date')
        contribution_amount_str = request.form.get('contribution_amount')

        if contribution_amount_str:
            contribution_amount = float(contribution_amount_str)
        else:
            flash('Le montant de la cotisation est requis.', 'error')
            return redirect(url_for('app_routes.group'))

        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        else:
            flash('La date de début est requise.', 'error')
            return redirect(url_for('app_routes.group'))

        new_group = Group(name=group_name, contribution_frequency=contribution_frequency, 
                          start_date=start_date, contribution_amount=contribution_amount)
        db.session.add(new_group)
        db.session.commit()

        membership = GroupMembership(user_id=user.id, group_id=new_group.id, role='admin')
        db.session.add(membership)
        db.session.commit()

        flash('Groupe créé avec succès !', 'success')
        return redirect(url_for('app_routes.group'))

    user_memberships = GroupMembership.query.filter_by(user_id=user.id).all()
    user_groups = [membership.group for membership in user_memberships]

    admin_status = {group.id: membership.role == 'admin' for membership in user_memberships for group in user_groups if membership.group_id == group.id}

    return render_template('group.html', 
                           groups=user_groups,
                           user=user,
                           pending_invitations_count=pending_invitations_count,
                           admin_status=admin_status)

@app_routes.route('/transaction', methods=['GET', 'POST'])
def transaction():
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))
    
    user = db.session.get(User, session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    
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
        
        is_admin = GroupMembership.query.filter_by(
            user_id=user.id,
            group_id=group_id,
            role='admin'
        ).first()
        
        if not is_admin:
            flash('Vous devez être administrateur pour effectuer des transactions', 'error')
            return redirect(url_for('app_routes.transaction'))
        
        final_amount = amount if transaction_type == 'deposit' else -amount
        
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
        return redirect(url_for('app_routes.transaction'))

    return render_template('new_transaction.html', 
                           group=group, 
                           members=members,
                           pending_invitations_count=pending_invitations_count)

@app_routes.route('/balance/<int:group_id>')
def balance(group_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    user = db.session.get(User, session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    group = Group.query.get_or_404(group_id)
    
    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id
    ).first()
    
    if not membership:
        flash('Vous n\'avez pas accès à ce groupe', 'error')
        return redirect(url_for('app_routes.group'))
    
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

@app_routes.route('/group/<int:group_id>/members', methods=['GET', 'POST', 'DELETE'])
def manage_members(group_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))
    
    user = db.session.get(User, session['user_id'])
    pending_invitations_count = get_pending_invitations_count(user.id)
    group = Group.query.get_or_404(group_id)
    
    # Vérifier si l'utilisateur est admin du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id,
        role='admin'
    ).first()
    
    if not membership:
        return redirect(url_for('app_routes.group'))
    
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

@app_routes.route('/invitations', methods=['GET', 'POST'])
def invitations():
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))
    
    user = db.session.get(User, session['user_id'])
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
        return redirect(url_for('app_routes.invitations'))
    
    pending_invitations = GroupInvitation.query.filter_by(
        user_id=user.id,
        status='pending'
    ).all()
    
    return render_template('invitations.html',
                         user=user,
                         invitations=pending_invitations,
                         pending_invitations_count=pending_invitations_count)

@app_routes.route('/search_users')
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





@app_routes.route('/get_invitation_count')
def get_invitation_count():
    if 'user_id' not in session:
        return jsonify({'count': 0})
    
    count = get_pending_invitations_count(session['user_id'])
    return jsonify({'count': count})

@app_routes.route('/get_group_members/<int:group_id>')
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

@app_routes.route('/group/<int:group_id>/details')
def group_details(group_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    user = db.session.get(User, session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id
    ).first()

    if not membership:
        flash('Vous n\'avez pas accès à ce groupe', 'error')
        return redirect(url_for('app_routes.group'))

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

@app_routes.route('/transaction/edit/<int:transaction_id>', methods=['GET', 'POST'])
def edit_transaction(transaction_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    transaction = Transaction.query.get_or_404(transaction_id)
    user = db.session.get(User, session['user_id'])

    # Vérifier si l'utilisateur est admin du groupe de la transaction
    is_admin = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=transaction.group_id,
        role='admin'
    ).first()

    if not is_admin:
        flash('Vous devez être administrateur pour modifier cette transaction', 'error')
        return redirect(url_for('app_routes.group_transactions', group_id=transaction.group_id))

    if request.method == 'POST':
        transaction.member_id = request.form.get('member_id')
        transaction.amount = float(request.form.get('amount'))
        transaction.description = request.form.get('description')
        transaction.type = request.form.get('type')
        transaction.date = datetime.strptime(request.form.get('transaction_date'), '%Y-%m-%d')
        
        db.session.commit()
        flash('Transaction modifiée avec succès!', 'success')
        return redirect(url_for('app_routes.group_transactions', group_id=transaction.group_id))

    members = db.session.query(User).join(GroupMembership).filter(GroupMembership.group_id == transaction.group_id).all()
    group = Group.query.get(transaction.group_id)  # Récupérer le groupe associé à la transaction
    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('edit_transaction.html', 
                           transaction=transaction, 
                           members=members, 
                           group=group,
                           pending_invitations_count=pending_invitations_count)

@app_routes.route('/transaction/delete/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    transaction = Transaction.query.get_or_404(transaction_id)
    user = db.session.get(User, session['user_id'])

    # Vérifier si l'utilisateur est admin du groupe de la transaction
    is_admin = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=transaction.group_id,
        role='admin'
    ).first()

    if not is_admin:
        flash('Vous devez être administrateur pour supprimer cette transaction', 'error')
        return redirect(url_for('app_routes.transaction'))

    db.session.delete(transaction)
    db.session.commit()
    flash('Transaction supprimée avec succès!', 'success')
    return redirect(url_for('app_routes.transaction'))





@app_routes.route('/group/<int:group_id>/transactions', methods=['GET', 'POST'])
def group_transactions(group_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))
    
    user = db.session.get(User, session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id
    ).first()

    if not membership:
        flash('Vous n\'avez pas accès à ce groupe', 'error')
        return redirect(url_for('app_routes.group'))

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
        
        # Créer une nouvelle transaction
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
        return redirect(url_for('app_routes.group_transactions_blueprint.group_transactions', group_id=group_id))

    members = db.session.query(User).join(GroupMembership).filter(GroupMembership.group_id == group_id).all()
    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('transaction.html',
                           group=group,
                           transactions=transactions,
                           members=members,
                           user=user,
                           is_admin=is_admin,
                           pending_invitations_count=pending_invitations_count)

@app_routes.route('/group/<int:group_id>/add_transaction', methods=['GET', 'POST'])
def add_transaction(group_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))
    
    user = db.session.get(User, session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est admin du groupe
    is_admin = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id,
        role='admin'
    ).first()

    if not is_admin:
        flash('Vous devez être administrateur pour ajouter des transactions', 'error')
        return redirect(url_for('app_routes.group_transactions', group_id=group_id))

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
        return redirect(url_for('app_routes.group_transactions', group_id=group_id))

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

@app_routes.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    user = db.session.get(User, session['user_id'])
    if user.role != 'admin':
        flash('Accès refusé : vous devez être administrateur pour accéder à cette page.', 'error')
        return redirect(url_for('app_routes.acceuil'))

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

@app_routes.route('/api/group/<int:group_id>/payments')
def get_group_payments(group_id):
    if 'user_id' not in session:
        return jsonify([])

    group = Group.query.get_or_404(group_id)
    payments = []

    for member in group.members:
        user = User.query.get(member.user_id)
        # Calculer les paiements effectués par le membre
        paid_amount = db.session.query(db.func.sum(Transaction.amount))\
            .filter(Transaction.member_id == user.id, Transaction.group_id == group.id, Transaction.type == 'deposit').scalar() or 0

        # Calculer les périodes de cotisation
        now = datetime.now(timezone.utc).date()
        start_date = group.start_date
        frequency = group.contribution_frequency

        if frequency == 'daily':
            periods = (now - start_date).days
        elif frequency == 'weekly':
            periods = (now - start_date).days // 7
        elif frequency == 'monthly':
            periods = (now.year - start_date.year) * 12 + now.month - start_date.month

        # Calculer le nombre de périodes payées
        paid_periods = paid_amount // group.contribution_amount

        # Ajouter les périodes payées en vert
        for i in range(int(paid_periods)):
            period_start = start_date + timedelta(days=i) if frequency == 'daily' else \
                           start_date + timedelta(weeks=i) if frequency == 'weekly' else \
                           start_date.replace(month=start_date.month + i)
            payments.append({
                'title': f'{user.username} a cotisé',
                'start': period_start.strftime('%Y-%m-%d'),
                'color': 'green'
            })

        # Ajouter les périodes non payées en rouge
        for i in range(int(paid_periods), int(periods)):
            period_start = start_date + timedelta(days=i) if frequency == 'daily' else \
                           start_date + timedelta(weeks=i) if frequency == 'weekly' else \
                           start_date.replace(month=start_date.month + i)
            payments.append({
                'title': f'{user.username} n\'a pas cotisé',
                'start': period_start.strftime('%Y-%m-%d'),
                'color': 'red'
            })

    return jsonify(payments)

@app_routes.route('/group/<int:group_id>/member/<int:member_id>/calendar')
def member_calendar(group_id, member_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))

    group = Group.query.get_or_404(group_id)
    member = User.query.get_or_404(member_id)

    # Vérifier si l'utilisateur est membre du groupe
    membership = GroupMembership.query.filter_by(
        user_id=member.id,
        group_id=group_id
    ).first()

    if not membership:
        flash('Ce membre n\'appartient pas à ce groupe', 'error')
        return redirect(url_for('app_routes.group'))

    # Récupérer le nombre d'invitations en attente
    pending_invitations_count = get_pending_invitations_count(session['user_id'])

    return render_template('member_calendar.html', group=group, member=member, pending_invitations_count=pending_invitations_count)



@app_routes.route('/group/<int:group_id>/new_transaction', methods=['GET', 'POST'])
def new_transaction(group_id):
    if 'user_id' not in session:
        return redirect(url_for('app_routes.connexion'))
    
    user = db.session.get(User, session['user_id'])
    group = Group.query.get_or_404(group_id)

    # Vérifier si l'utilisateur est admin du groupe
    membership = GroupMembership.query.filter_by(
        user_id=user.id,
        group_id=group_id,
        role='admin'
    ).first()

    if not membership:
        flash('Accès refusé : vous devez être administrateur pour ajouter une transaction.', 'error')
        return redirect(url_for('app_routes.group_transactions', group_id=group_id))

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
        
        # Créer une nouvelle transaction
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
        return redirect(url_for('app_routes.group_transactions', group_id=group_id))

    members = db.session.query(User).join(GroupMembership).filter(GroupMembership.group_id == group_id).all()
    pending_invitations_count = get_pending_invitations_count(user.id)

    return render_template('new_transaction.html', 
                           group=group, 
                           members=members,
                           pending_invitations_count=pending_invitations_count)