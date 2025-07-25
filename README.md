# 📋 Gerenciador de Demandas

Sistema de gerenciamento de tarefas e demandas com cronômetro integrado.

## 🚀 Funcionalidades

- ✅ Criar, editar e excluir tarefas
- 📊 Dashboard com estatísticas
- ⏱️ Cronômetro para rastreamento de tempo
- 🏷️ Categorias e tags
- 📱 Interface responsiva com Tailwind CSS
- 💬 Sistema de comentários
- 📈 Controle de progresso
- 🎯 Filtros e ordenação

## 🛠️ Tecnologias

- **Backend**: Python Flask + SQLAlchemy
- **Frontend**: Tailwind CSS + JavaScript vanilla
- **Database**: SQLite (local) / PostgreSQL (produção)
- **Deploy**: Render.com

## 📦 Instalação Local

```bash
# Clone o repositório
git clone https://github.com/SEU-USUARIO/demandas-app.git
cd demandas-app

# Instale as dependências
pip install -r requirements.txt

# Execute a aplicação
python app_no_auth.py
```

Acesse: http://localhost:5000

## 🌐 Deploy

Deploy automático via Render.com configurado com:

- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app_no_auth:app`
- PostgreSQL database integrado

## 📱 Responsivo

Interface otimizada para:

- 💻 Desktop
- 📱 Mobile
- 📟 Tablet

## 🔧 Configuração

O sistema detecta automaticamente o ambiente:

- **Desenvolvimento**: SQLite local
- **Produção**: PostgreSQL via DATABASE_URL

---

Desenvolvido com ❤️ para gerenciamento eficiente de demandas!
