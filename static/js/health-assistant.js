(() => {
  const form = document.getElementById('chat-form');
  const input = document.getElementById('chat-input');
  const messages = document.getElementById('chat-messages');
  const sendButton = document.getElementById('chat-send');
  const loading = document.getElementById('chat-loading');
  const errorBox = document.getElementById('chat-error');
  const clearButton = document.getElementById('clear-chat');
  const refreshPlanButton = document.getElementById('refresh-plan');
  const welcomeMessage = messages.querySelector('[data-welcome="true"]');

  if (!form || !input || !messages || !sendButton || !loading || !errorBox || !clearButton || !welcomeMessage) {
    return;
  }

  const createArticle = (isUser) => {
    const article = document.createElement('article');
    article.className = `ht-chat-message ${isUser ? 'ht-chat-user' : 'ht-chat-assistant'}`;

    const avatar = document.createElement('span');
    avatar.className = 'ht-message-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    const icon = document.createElement('i');
    icon.className = isUser ? 'fa-solid fa-user' : 'fa-solid fa-heart-pulse';
    avatar.append(icon);

    const content = document.createElement('div');
    content.className = 'ht-message-content';
    const label = document.createElement('strong');
    label.textContent = isUser ? 'You' : 'Health Assistant';
    content.append(label);
    article.append(avatar, content);
    return { article, content };
  };

  const addMessage = (text, isUser) => {
    const { article, content } = createArticle(isUser);
    const paragraph = document.createElement('p');
    paragraph.textContent = text;
    content.append(paragraph);
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  };

  const addList = (container, title, entries, className) => {
    if (!Array.isArray(entries) || entries.length === 0) {
      return;
    }
    const section = document.createElement('section');
    section.className = className;
    const heading = document.createElement('h3');
    heading.textContent = title;
    const list = document.createElement('ul');
    entries.forEach((entry) => {
      const item = document.createElement('li');
      item.textContent = entry;
      list.append(item);
    });
    section.append(heading, list);
    container.append(section);
  };

  const addPlan = (plan) => {
    const { article, content } = createArticle(false);
    content.classList.add('ht-structured-content');
    const title = document.createElement('h2');
    title.textContent = plan.title;
    const date = document.createElement('p');
    date.className = 'ht-structured-date';
    date.textContent = `For ${plan.date}`;
    content.append(title, date);

    const groups = new Map();
    (Array.isArray(plan.items) ? plan.items : []).forEach((recommendation) => {
      if (!recommendation || typeof recommendation.category !== 'string') return;
      if (!groups.has(recommendation.category)) groups.set(recommendation.category, []);
      groups.get(recommendation.category).push(recommendation);
    });
    groups.forEach((items, category) => {
      const section = document.createElement('section');
      section.className = 'ht-plan-category';
      const heading = document.createElement('h3');
      heading.textContent = category;
      section.append(heading);
      items.forEach((recommendation) => {
        const card = document.createElement('div');
        card.className = 'ht-plan-item';
        const itemTitle = document.createElement('strong');
        itemTitle.textContent = recommendation.title || 'Suggestion';
        const suggestion = document.createElement('p');
        suggestion.textContent = recommendation.suggestion || '';
        const reason = document.createElement('p');
        reason.className = 'ht-plan-reason';
        reason.textContent = `Why this was selected: ${recommendation.reason || 'Based on your records.'}`;
        card.append(itemTitle, suggestion, reason);
        section.append(card);
      });
      content.append(section);
    });

    addList(content, 'Recorded information', plan.recorded_summary, 'ht-plan-recorded');
    addList(content, 'Not recorded', plan.missing_data, 'ht-plan-missing');
    if (typeof plan.disclaimer === 'string') {
      const disclaimer = document.createElement('p');
      disclaimer.className = 'ht-plan-disclaimer';
      disclaimer.textContent = plan.disclaimer;
      content.append(disclaimer);
    }
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  };

  const addProgress = (progress) => {
    const { article, content } = createArticle(false);
    content.classList.add('ht-structured-content');
    const title = document.createElement('h2');
    title.textContent = progress.title;
    const date = document.createElement('p');
    date.className = 'ht-structured-date';
    date.textContent = `For ${progress.date}`;
    content.append(title, date);
    addList(content, 'Recorded information', progress.recorded_summary, 'ht-plan-recorded');
    addList(content, 'Not recorded', progress.missing_data, 'ht-plan-missing');
    addList(content, 'Possible next steps', progress.next_steps, 'ht-plan-next');
    messages.append(article);
    messages.scrollTop = messages.scrollHeight;
  };

  const requestAnswer = async (message) => {
    errorBox.hidden = true;
    errorBox.textContent = '';
    addMessage(message, true);
    input.value = '';
    input.style.height = '';
    sendButton.disabled = true;
    loading.hidden = false;
    messages.scrollTop = messages.scrollHeight;

    try {
      const response = await fetch(form.dataset.endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value,
        },
        body: new URLSearchParams({ message }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'The question could not be processed. Please try again.');
      }
      if (result.type === 'wellness_plan') {
        addPlan(result);
      } else if (result.type === 'progress') {
        addProgress(result);
      } else if (typeof result.reply === 'string') {
        addMessage(result.reply, false);
      } else {
        throw new Error('The assistant returned an unexpected response. Please try again.');
      }
    } catch (error) {
      errorBox.textContent = error.message || 'Unable to connect to the assistant. Please try again.';
      errorBox.hidden = false;
    } finally {
      loading.hidden = true;
      sendButton.disabled = false;
      input.focus();
    }
  };

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) {
      errorBox.textContent = 'Enter a question before sending.';
      errorBox.hidden = false;
      input.focus();
      return;
    }
    input.value = '';
    input.style.height = '';
    await requestAnswer(message);
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
  });

  document.querySelectorAll('[data-question]').forEach((button) => {
    button.addEventListener('click', () => {
      if (sendButton.disabled) return;
      requestAnswer(button.dataset.question);
    });
  });

  refreshPlanButton.addEventListener('click', () => {
    if (!sendButton.disabled) requestAnswer('What should I do today?');
  });

  clearButton.addEventListener('click', () => {
    messages.replaceChildren(welcomeMessage.cloneNode(true));
    errorBox.hidden = true;
    errorBox.textContent = '';
    input.value = '';
    input.style.height = '';
    input.focus();
  });
})();
