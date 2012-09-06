import webapp2

from . import authorized, model_register, render, utils


class BaseRequestHandler(webapp2.RequestHandler):
  def handle_exception(self, exception, debug_mode):
    if isinstance(exception, utils.Http404):
      self.error(exception.code)
      path = '%s.html' % exception.code
      self.render(path, {'errorpage': True})
      return
    super(BaseRequestHandler, self).handle_exception(exception, debug_mode)

  def render(self, path, template_kwargs={}):
    template_kwargs['uri_for'] = lambda route_name, *a, **kw: self.uri_for('appengine_admin.%s' % route_name, *a, **kw)
    template_kwargs['handler'] = self
    if hasattr(self, 'models'):
      template_kwargs['models'] = self.models
    self.response.out.write(render.template(path, template_kwargs))

  def redirect_admin(self, route_name, *args, **kwargs):
    self.redirect(self.uri_for('appengine_admin.%s' % route_name, *args, **kwargs))


class Admin(BaseRequestHandler):
  '''Use this class as the central view in your app routing.

  Example:
  ===
  import appengine_admin

  application = webapp2.WSGIApplication([
    ...
    # Admin pages
    (r'^(/admin/models)(.*)$', appengine_admin.Admin),
    ...
  ], debug = settings.DEBUG)
  ===
  '''

  def __init__(self, *args, **kwargs):
    super(Admin, self).__init__(*args, **kwargs)
    self.models = model_register._model_register.keys()
    self.models.sort()

  @authorized.check()
  def index(self):
    '''Admin start page.'''
    self.render('index.html', {
      'models': self.models,
    })

  @authorized.check()
  def list(self, model_name):
    '''List entities for a model by name.'''
    model_admin = model_register.get_model_admin(model_name)
    paginator = utils.Paginator(model_admin=model_admin)
    # Get only those items that should be displayed in current page
    page = paginator.get_page(request=self.request)
    items = list(page)
    self.render('model_item_list.html', {
      'model_name': model_admin.model_name,
      'list_properties': model_admin._list_properties,
      'items': map(model_admin._attachListFields, items),
      'page': page,
    })

  @authorized.check()
  def new(self, model_name):
    '''Handle creating a new record for a particular model.'''
    model_admin = model_register.get_model_admin(model_name)
    if self.request.method == 'POST':
      item_form = model_admin.AdminForm(data=self.request.POST)
      if item_form.is_valid():
        # Save the data, and redirect to the edit page
        item = item_form.save()
        self.redirect_admin('edit', model_name=model_admin.model_name, key=item.key())
        return
    else:
      item_form = model_admin.AdminForm()

    template_kwargs = {
      'item': None,
      'model_name': model_admin.model_name,
      'item_form': item_form,
      'readonly_properties': model_admin._readonly_properties,
    }
    self.render('model_item_edit.html', template_kwargs)

  @authorized.check()
  def edit(self, model_name, key):
    '''Edit an editing existing record for a particular model.

    Raise Http404 if record is not found.
    '''
    model_admin = model_register.get_model_admin(model_name)
    item = utils.safe_get_by_key(model_admin.model, key)

    if self.request.method == 'POST':
      item_form = model_admin.AdminForm(data=self.request.POST, instance=item)
      if item_form.is_valid():
        # Save the data, and redirect to the edit page
        item = item_form.save()
        self.redirect_admin('edit', model_name=model_admin.model_name, key=item.key())
        return
    else:
      item_form = model_admin.AdminForm(instance=item)

    template_kwargs = {
      'item': item,
      'model_name': model_admin.model_name,
      'item_form': item_form,
      'readonly_properties': utils.get_readonly_properties_with_values(item, model_admin),
    }
    self.render('model_item_edit.html', template_kwargs)

  @authorized.check()
  def delete(self, model_name, key):
    '''Delete a record for a particular model.

    Raises Http404 if the record not found.
    '''
    model_admin = model_register.get_model_admin(model_name)
    item = utils.safe_get_by_key(model_admin.model, key)
    item.delete()
    self.redirect_admin('list', model_name=model_admin.model_name)

  @authorized.check()
  def blob(self, model_name, field_name, key):
    '''Returns blob field contents.'''
    model_admin = model_register.get_model_admin(model_name)
    item = utils.safe_get_by_key(model_admin.model, key)
    data = getattr(item, field_name, None)
    if data is None:
      raise utils.Http404()

    props = utils.get_blob_properties(item, field_name)
    if props:
      self.response.headers['Content-Type'] = props['Content_Type']
      self.response.headers['Content-Disposition'] = 'inline; filename=%s' % props['File_Name']
    else:
      self.response.headers['Content-Type'] = 'application/octet-stream'
    self.response.out.write(data)