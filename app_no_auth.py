from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import json
import secrets
import os
from datetime import datetime, timedelta
from sqlalchemy import case, and_, or_, func, desc

app = Flask(__name__)

# Configurações
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

# Configuração do banco de dados - detecta ambiente automaticamente
if os.environ.get('DATABASE_URL'):
    # Produção (Render, Heroku, etc.) - PostgreSQL
    database_url = os.environ.get('DATABASE_URL')
    # Corrigir URL do PostgreSQL se necessário
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Desenvolvimento - SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///demandas_simple.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32MB

# Extensões
db = SQLAlchemy(app)

# Criar diretórios
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Modelos simplificados
class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text)
    priority = db.Column(db.String(20), nullable=False, index=True)  # critico, alta, media, baixa
    status = db.Column(db.String(20), nullable=False, index=True)    # pendente, andamento, concluido, cancelado
    category = db.Column(db.String(50), default='geral', index=True)
    due_date = db.Column(db.DateTime, index=True)
    estimated_hours = db.Column(db.Float, default=0)
    actual_hours = db.Column(db.Float, default=0)
    progress = db.Column(db.Integer, default=0)  # 0-100%
    tags = db.Column(db.Text)  # JSON string
    order_index = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Campos expandidos
    difficulty = db.Column(db.String(20), default='facil')  # facil, medio, dificil
    reminder_date = db.Column(db.DateTime)
    attachments = db.Column(db.Text)  # JSON string
    notes = db.Column(db.Text)
    color = db.Column(db.String(7), default='#007bff')
    
    # Relacionamentos
    comments = db.relationship('Comment', backref='task', lazy='dynamic', cascade='all, delete-orphan')
    
    def get_tags_list(self):
        if self.tags:
            try:
                return json.loads(self.tags)
            except:
                return []
        return []
    
    def set_tags_list(self, tags_list):
        self.tags = json.dumps(tags_list) if tags_list else None
    
    def get_attachments_list(self):
        if self.attachments:
            try:
                return json.loads(self.attachments)
            except:
                return []
        return []
    
    def set_attachments_list(self, attachments_list):
        self.attachments = json.dumps(attachments_list) if attachments_list else None
    
    def is_overdue(self):
        if self.due_date and self.status not in ['concluido', 'cancelado']:
            return datetime.now() > self.due_date
        return False
    
    def days_until_due(self):
        if self.due_date:
            delta = self.due_date - datetime.now()
            return delta.days
        return None
    
    def get_priority_weight(self):
        weights = {'critico': 4, 'alta': 3, 'media': 2, 'baixa': 1}
        return weights.get(self.priority, 1)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    author_name = db.Column(db.String(100), default='Usuário')

# Context processor para variáveis globais
@app.context_processor
def inject_globals():
    return {
        'datetime': datetime,
        'len': len,
        'enumerate': enumerate,
    }

# Criar tabelas
with app.app_context():
    db.create_all()

# Rotas principais
@app.route('/')
def dashboard():
    """Dashboard principal - página inicial"""
    
    # Busca e filtros
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    category_filter = request.args.get('category', '')
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    view_mode = request.args.get('view', 'list')
    
    # Query base
    query = Task.query
    
    # Aplicar filtros
    if search:
        query = query.filter(
            or_(
                Task.title.contains(search),
                Task.description.contains(search),
                Task.category.contains(search)
            )
        )
    
    if status_filter:
        query = query.filter(Task.status == status_filter)
    
    if priority_filter:
        query = query.filter(Task.priority == priority_filter)
    
    if category_filter:
        query = query.filter(Task.category == category_filter)
    
    # Aplicar ordenação
    if sort_order == 'desc':
        if sort_by == 'priority':
            query = query.order_by(desc(Task.priority))
        elif sort_by == 'due_date':
            query = query.order_by(desc(Task.due_date))
        else:
            query = query.order_by(desc(getattr(Task, sort_by)))
    else:
        if sort_by == 'priority':
            query = query.order_by(Task.priority)
        elif sort_by == 'due_date':
            query = query.order_by(Task.due_date)
        else:
            query = query.order_by(getattr(Task, sort_by))
    
    tasks = query.all()
    
    # Estatísticas
    total_tasks = Task.query.count()
    pending_tasks = Task.query.filter_by(status='pendente').count()
    in_progress_tasks = Task.query.filter_by(status='andamento').count()
    completed_tasks = Task.query.filter_by(status='concluido').count()
    overdue_tasks = Task.query.filter(
        and_(
            Task.due_date < datetime.now(),
            Task.status.in_(['pendente', 'andamento'])
        )
    ).count()
    
    # Categorias para filtro
    categories = db.session.query(Task.category).distinct().all()
    categories = [cat[0] for cat in categories if cat[0]]
    
    # Tarefas por status para view Kanban
    tasks_by_status = {
        'pendente': Task.query.filter_by(status='pendente').all(),
        'andamento': Task.query.filter_by(status='andamento').all(),
        'concluido': Task.query.filter_by(status='concluido').all(),
        'cancelado': Task.query.filter_by(status='cancelado').all()
    }
    
    stats = {
        'total': total_tasks,
        'pending': pending_tasks,
        'in_progress': in_progress_tasks,
        'completed': completed_tasks,
        'overdue': overdue_tasks,
        'completion_rate': round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)
    }
    
    return render_template('dashboard/index.html', 
                         tasks=tasks,
                         tasks_by_status=tasks_by_status,
                         stats=stats,
                         categories=categories,
                         search=search,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         category_filter=category_filter,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         view_mode=view_mode)

@app.route('/task/new', methods=['GET', 'POST'])
def new_task():
    """Formulário para nova tarefa e criação"""
    if request.method == 'POST':
        try:
            # Processar tags
            tags_str = request.form.get('tags', '')
            tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            
            # Processar data
            due_date = None
            if request.form.get('due_date'):
                date_str = request.form.get('due_date')
                try:
                    # Tentar formato com hora primeiro
                    if 'T' in date_str:
                        due_date = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
                    else:
                        due_date = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError as e:
                    print(f"Erro ao processar data: {date_str}, erro: {e}")
                    # Se falhar, tentar apenas a parte da data
                    due_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            
            # Processar horas estimadas
            estimated_hours = 0
            if request.form.get('estimated_hours'):
                try:
                    estimated_hours = float(request.form.get('estimated_hours'))
                except ValueError:
                    estimated_hours = 0
            
            task = Task(
                title=request.form.get('title'),
                description=request.form.get('description', ''),
                priority=request.form.get('priority', 'media'),
                status=request.form.get('status', 'pendente'),
                category=request.form.get('category', 'geral'),
                due_date=due_date,
                estimated_hours=estimated_hours
            )
            
            # Definir tags se houver
            if tags_list:
                task.set_tags_list(tags_list)
            
            db.session.add(task)
            db.session.commit()
            
            flash('Tarefa criada com sucesso!', 'success')
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            flash(f'Erro ao criar tarefa: {str(e)}', 'error')
            return redirect(url_for('new_task'))
        
    return render_template('dashboard/task_form.html', task=None)

@app.route('/task/<int:task_id>')
def task_detail(task_id):
    """Detalhes da tarefa"""
    task = Task.query.get_or_404(task_id)
    comments = Comment.query.filter_by(task_id=task_id).order_by(Comment.created_at.desc()).all()
    
    return render_template('dashboard/task_detail.html', task=task, comments=comments)

@app.route('/task/<int:task_id>/edit', methods=['GET', 'POST'])
def edit_task(task_id):
    """Formulário de edição e atualização"""
    task = Task.query.get_or_404(task_id)
    
    if request.method == 'POST':
        try:
            # Processar tags
            tags_str = request.form.get('tags', '')
            tags_list = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
            
            # Processar data
            due_date = None
            if request.form.get('due_date'):
                date_str = request.form.get('due_date')
                try:
                    # Tentar formato com hora primeiro
                    if 'T' in date_str:
                        due_date = datetime.strptime(date_str.split('T')[0], '%Y-%m-%d')
                    else:
                        due_date = datetime.strptime(date_str, '%Y-%m-%d')
                except ValueError as e:
                    print(f"Erro ao processar data: {date_str}, erro: {e}")
                    # Se falhar, tentar apenas a parte da data
                    due_date = datetime.strptime(date_str[:10], '%Y-%m-%d')
            
            # Processar horas estimadas
            estimated_hours = 0
            if request.form.get('estimated_hours'):
                try:
                    estimated_hours = float(request.form.get('estimated_hours'))
                except ValueError:
                    estimated_hours = 0

            # Processar horas trabalhadas
            actual_hours = 0
            if request.form.get('actual_hours'):
                try:
                    actual_hours = float(request.form.get('actual_hours'))
                except ValueError:
                    actual_hours = 0
            
            # Processar progresso
            progress = 0
            if request.form.get('progress'):
                try:
                    progress = int(request.form.get('progress'))
                    progress = max(0, min(100, progress))  # Garantir que está entre 0-100
                except ValueError:
                    progress = 0
            
            # Atualizar campos
            task.title = request.form.get('title')
            task.description = request.form.get('description', '')
            task.priority = request.form.get('priority', 'media')
            task.status = request.form.get('status', 'pendente')
            task.category = request.form.get('category', 'geral')
            task.due_date = due_date
            task.estimated_hours = estimated_hours
            task.actual_hours = actual_hours
            task.progress = progress
            task.updated_at = datetime.utcnow()
            
            # Definir tags se houver
            if tags_list:
                task.set_tags_list(tags_list)
            
            db.session.commit()
            
            flash('Tarefa atualizada com sucesso!', 'success')
            return redirect(url_for('task_detail', task_id=task_id))
            
        except Exception as e:
            flash(f'Erro ao atualizar tarefa: {str(e)}', 'error')
            return redirect(url_for('edit_task', task_id=task_id))
    
    return render_template('dashboard/task_form.html', task=task)

@app.route('/task/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    """Excluir tarefa"""
    task = Task.query.get_or_404(task_id)
    
    try:
        db.session.delete(task)
        db.session.commit()
        
        flash('Tarefa excluída com sucesso!', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f'Erro ao excluir tarefa: {str(e)}', 'error')
        return redirect(url_for('task_detail', task_id=task_id))

@app.route('/task/<int:task_id>/comment', methods=['POST'])
def add_comment(task_id):
    """Adicionar comentário"""
    task = Task.query.get_or_404(task_id)
    
    try:
        comment = Comment(
            content=request.form.get('content'),
            task_id=task_id,
            author_name=request.form.get('author_name', 'Usuário')
        )
        
        db.session.add(comment)
        db.session.commit()
        
        flash('Comentário adicionado!', 'success')
        
    except Exception as e:
        flash(f'Erro ao adicionar comentário: {str(e)}', 'error')
    
    return redirect(url_for('task_detail', task_id=task_id))

# API endpoints para AJAX
@app.route('/api/task/<int:task_id>/timer/start', methods=['POST'])
def start_timer(task_id):
    """Iniciar cronômetro da tarefa"""
    task = Task.query.get_or_404(task_id)
    
    # Verificar se já tem um timer ativo
    session_key = f'timer_task_{task_id}'
    if session_key in request.cookies:
        return jsonify({'success': False, 'message': 'Timer já está ativo'}), 400
    
    # Marcar como "em andamento" se estiver pendente
    if task.status == 'pendente':
        task.status = 'andamento'
        db.session.commit()
    
    # Retornar timestamp atual
    start_time = datetime.utcnow().timestamp()
    
    response = jsonify({
        'success': True,
        'message': 'Timer iniciado!',
        'start_time': start_time,
        'task_status': task.status
    })
    
    # Definir cookie para persistir o timer
    response.set_cookie(session_key, str(start_time), max_age=86400)  # 24 horas
    
    return response

@app.route('/api/task/<int:task_id>/timer/stop', methods=['POST'])
def stop_timer(task_id):
    """Parar cronômetro e adicionar tempo à tarefa"""
    task = Task.query.get_or_404(task_id)
    
    session_key = f'timer_task_{task_id}'
    start_time_str = request.cookies.get(session_key)
    
    if not start_time_str:
        return jsonify({'success': False, 'message': 'Nenhum timer ativo'}), 400
    
    try:
        start_time = float(start_time_str)
        end_time = datetime.utcnow().timestamp()
        elapsed_seconds = end_time - start_time
        elapsed_hours = elapsed_seconds / 3600
        
        # Adicionar tempo trabalhado
        task.actual_hours = (task.actual_hours or 0) + elapsed_hours
        task.updated_at = datetime.utcnow()
        db.session.commit()
        
        response = jsonify({
            'success': True,
            'message': f'{elapsed_hours:.2f} horas adicionadas!',
            'elapsed_seconds': elapsed_seconds,
            'elapsed_hours': elapsed_hours,
            'total_hours': task.actual_hours
        })
        
        # Remover cookie do timer
        response.set_cookie(session_key, '', expires=0)
        
        return response
        
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Erro ao processar timer'}), 400

@app.route('/api/task/<int:task_id>/timer/status', methods=['GET'])
def timer_status(task_id):
    """Verificar status do cronômetro"""
    session_key = f'timer_task_{task_id}'
    start_time_str = request.cookies.get(session_key)
    
    if start_time_str:
        try:
            start_time = float(start_time_str)
            current_time = datetime.utcnow().timestamp()
            elapsed_seconds = current_time - start_time
            
            return jsonify({
                'active': True,
                'start_time': start_time,
                'elapsed_seconds': elapsed_seconds
            })
        except (ValueError, TypeError):
            pass
    
    return jsonify({'active': False})

@app.route('/test-timer')
def test_timer():
    """Página de teste do cronômetro"""
    with open('test_timer.html', 'r', encoding='utf-8') as f:
        content = f.read()
    return content

@app.route('/debug-timer')
def debug_timer():
    """Página de debug do cronômetro"""
    with open('debug_timer.html', 'r', encoding='utf-8') as f:
        content = f.read()
    return content

@app.route('/create-sample-data')
def create_sample_data():
    """Criar dados de exemplo para teste"""
    try:
        # Verificar se já existem tarefas
        if Task.query.count() > 0:
            return jsonify({'message': 'Dados já existem', 'count': Task.query.count()})
        
        # Criar tarefas de exemplo
        sample_tasks = [
            {
                'title': 'Desenvolver nova funcionalidade',
                'description': 'Implementar sistema de cronômetro para rastreamento de tempo',
                'priority': 'alta',
                'status': 'andamento',
                'category': 'desenvolvimento',
                'estimated_hours': 8.0,
                'color': '#28a745'
            },
            {
                'title': 'Revisar documentação',
                'description': 'Atualizar documentação do sistema com novas funcionalidades',
                'priority': 'media',
                'status': 'pendente',
                'category': 'documentacao',
                'estimated_hours': 4.0,
                'color': '#007bff'
            },
            {
                'title': 'Corrigir bug crítico',
                'description': 'Bug no sistema de autenticação precisa ser corrigido urgentemente',
                'priority': 'critico',
                'status': 'pendente',
                'category': 'bugfix',
                'estimated_hours': 2.0,
                'color': '#dc3545'
            },
            {
                'title': 'Melhorar interface mobile',
                'description': 'Otimizar a experiência do usuário em dispositivos móveis',
                'priority': 'media',
                'status': 'pendente',
                'category': 'ui/ux',
                'estimated_hours': 6.0,
                'color': '#ffc107'
            }
        ]
        
        for task_data in sample_tasks:
            task = Task(**task_data)
            db.session.add(task)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Dados de exemplo criados com sucesso!',
            'count': len(sample_tasks)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/task/<int:task_id>/status', methods=['POST'])
def update_task_status(task_id):
    """Atualizar status da tarefa via API"""
    task = Task.query.get_or_404(task_id)
    
    data = request.get_json()
    new_status = data.get('status')
    
    if new_status in ['pendente', 'andamento', 'concluido', 'cancelado']:
        task.status = new_status
        task.updated_at = datetime.utcnow()
        
        # Auto-ajustar progresso baseado no status
        if new_status == 'concluido':
            task.progress = 100
        elif new_status == 'pendente':
            task.progress = 0
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Status atualizado!',
            'status': task.status,
            'progress': task.progress
        })
    
    return jsonify({'success': False, 'message': 'Status inválido'}), 400

@app.route('/api/task/<int:task_id>/progress', methods=['POST'])
def update_task_progress(task_id):
    """Atualizar progresso da tarefa via API"""
    task = Task.query.get_or_404(task_id)
    
    data = request.get_json()
    new_progress = data.get('progress')
    
    if 0 <= new_progress <= 100:
        task.progress = new_progress
        task.updated_at = datetime.utcnow()
        
        # Auto-ajustar status baseado no progresso
        if new_progress == 100:
            task.status = 'concluido'
        elif new_progress > 0 and task.status == 'pendente':
            task.status = 'andamento'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Progresso atualizado!',
            'progress': task.progress,
            'status': task.status
        })
    
    return jsonify({'success': False, 'message': 'Progresso inválido'}), 400

@app.route('/api/search')
def api_search():
    """API de busca"""
    query = request.args.get('q', '')
    
    if len(query) < 2:
        return jsonify([])
    
    tasks = Task.query.filter(
        or_(
            Task.title.contains(query),
            Task.description.contains(query),
            Task.category.contains(query)
        )
    ).limit(10).all()
    
    results = []
    for task in tasks:
        results.append({
            'id': task.id,
            'title': task.title,
            'status': task.status,
            'priority': task.priority,
            'category': task.category,
            'url': url_for('task_detail', task_id=task.id)
        })
    
    return jsonify(results)

@app.route('/api/task/<int:task_id>/add_time', methods=['POST'])
def add_time_to_task(task_id):
    """Adicionar tempo trabalhado à tarefa"""
    task = Task.query.get_or_404(task_id)
    
    data = request.get_json()
    hours_to_add = data.get('hours', 0)
    
    try:
        hours_to_add = float(hours_to_add)
        if hours_to_add > 0:
            task.actual_hours = (task.actual_hours or 0) + hours_to_add
            task.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'{hours_to_add:.2f} horas adicionadas!',
                'actual_hours': task.actual_hours
            })
    except (ValueError, TypeError):
        pass
    
    return jsonify({'success': False, 'message': 'Tempo inválido'}), 400

@app.route('/api/stats')
def api_stats():
    """API de estatísticas"""
    total_tasks = Task.query.count()
    pending_tasks = Task.query.filter_by(status='pendente').count()
    in_progress_tasks = Task.query.filter_by(status='andamento').count()
    completed_tasks = Task.query.filter_by(status='concluido').count()
    
    return jsonify({
        'total': total_tasks,
        'pending': pending_tasks,
        'in_progress': in_progress_tasks,
        'completed': completed_tasks,
        'completion_rate': round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)
    })

# Tratamento de erros
@app.errorhandler(404)
def not_found(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    
    if debug:
        print("🚀 Gerenciador de Demandas iniciado!")
        print("📊 Acesse no PC: http://localhost:5000")
        print("📱 Acesse no celular: http://192.168.10.55:5000")
        print("💡 Sistema simplificado - sem autenticação")
    
    app.run(debug=debug, host='0.0.0.0', port=port)
