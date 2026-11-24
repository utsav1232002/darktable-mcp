/* SPDX-License-Identifier: GPL-3.0-or-later
 * Named blend editing for the pinned darktable engine. Included by dt_bridge.c.
 * A mask replacement creates fresh native forms. Other modules can keep using
 * the previous group and earlier history items retain their own snapshots. */
#include "develop/blend.h"
#include <math.h>

typedef struct
{
  const char *name;
  int value;
  int spaces;
} personal_option_t;
#define LAB (1 << DEVELOP_BLEND_CS_LAB)
#define DISP (1 << DEVELOP_BLEND_CS_RGB_DISPLAY)
#define SCENE (1 << DEVELOP_BLEND_CS_RGB_SCENE)
#define RAW (1 << DEVELOP_BLEND_CS_RAW)
#define ALL (LAB | DISP | SCENE | RAW)
#define OLD (LAB | DISP | RAW)
static const personal_option_t modes[] = {{"normal", DEVELOP_BLEND_NORMAL2, ALL},
                                          {"average", DEVELOP_BLEND_AVERAGE, ALL},
                                          {"difference", DEVELOP_BLEND_DIFFERENCE2, ALL},
                                          {"multiply", DEVELOP_BLEND_MULTIPLY, ALL},
                                          {"add", DEVELOP_BLEND_ADD, ALL},
                                          {"subtract", DEVELOP_BLEND_SUBTRACT, ALL},
                                          {"normal_bounded", DEVELOP_BLEND_BOUNDED, OLD},
                                          {"lighten", DEVELOP_BLEND_LIGHTEN, OLD},
                                          {"darken", DEVELOP_BLEND_DARKEN, OLD},
                                          {"screen", DEVELOP_BLEND_SCREEN, OLD},
                                          {"overlay", DEVELOP_BLEND_OVERLAY, OLD},
                                          {"soft_light", DEVELOP_BLEND_SOFTLIGHT, OLD},
                                          {"hard_light", DEVELOP_BLEND_HARDLIGHT, OLD},
                                          {"vivid_light", DEVELOP_BLEND_VIVIDLIGHT, OLD},
                                          {"linear_light", DEVELOP_BLEND_LINEARLIGHT, OLD},
                                          {"pin_light", DEVELOP_BLEND_PINLIGHT, OLD},
                                          {"divide", DEVELOP_BLEND_DIVIDE, SCENE},
                                          {"geometric_mean", DEVELOP_BLEND_GEOMETRIC_MEAN, SCENE},
                                          {"harmonic_mean", DEVELOP_BLEND_HARMONIC_MEAN, SCENE},
                                          {"lightness", DEVELOP_BLEND_LIGHTNESS, LAB | DISP | SCENE},
                                          {"chromaticity", DEVELOP_BLEND_CHROMATICITY, LAB | DISP | SCENE},
                                          {"red", DEVELOP_BLEND_RGB_R, DISP | SCENE},
                                          {"green", DEVELOP_BLEND_RGB_G, DISP | SCENE},
                                          {"blue", DEVELOP_BLEND_RGB_B, DISP | SCENE},
                                          {"hue", DEVELOP_BLEND_HUE, LAB | DISP},
                                          {"color", DEVELOP_BLEND_COLOR, LAB | DISP},
                                          {"color_adjustment", DEVELOP_BLEND_COLORADJUST, LAB | DISP},
                                          {"lab_lightness", DEVELOP_BLEND_LAB_LIGHTNESS, LAB},
                                          {"lab_a", DEVELOP_BLEND_LAB_A, LAB},
                                          {"lab_b", DEVELOP_BLEND_LAB_B, LAB},
                                          {"lab_color", DEVELOP_BLEND_LAB_COLOR, LAB},
                                          {"hsv_value", DEVELOP_BLEND_HSV_VALUE, DISP},
                                          {"hsv_color", DEVELOP_BLEND_HSV_COLOR, DISP},
                                          {NULL}};
static const personal_option_t channels[] = {{"luminance", 0, LAB | DISP | SCENE},
                                             {"red", 1, DISP | SCENE},
                                             {"green", 2, DISP | SCENE},
                                             {"blue", 3, DISP | SCENE},
                                             {"a", 1, LAB},
                                             {"b", 2, LAB},
                                             {"chroma", 8, LAB},
                                             {"hue", 9, LAB},
                                             {"hue", 8, DISP},
                                             {"saturation", 9, DISP},
                                             {"lightness", 10, DISP},
                                             {"lightness", 8, SCENE},
                                             {"chroma", 9, SCENE},
                                             {"hue", 10, SCENE},
                                             {NULL}};
static const char *const space_names[] = {"none", "raw", "lab", "display_rgb", "scene_rgb"};
static const char *const guide_names[] = {"input_before_blur", "output_before_blur", "input_after_blur",
                                          "output_after_blur"};
static const int guides[] = {DEVELOP_MASK_GUIDE_IN_BEFORE_BLUR, DEVELOP_MASK_GUIDE_OUT_BEFORE_BLUR,
                             DEVELOP_MASK_GUIDE_IN_AFTER_BLUR, DEVELOP_MASK_GUIDE_OUT_AFTER_BLUR};

static gboolean pb_fail(char **err, const char *field, const char *reason)
{
  _seterr(err, "blend.%s: %s", field, reason);
  return FALSE;
}
static gboolean pb_keys(JsonObject *obj, const char *const *allowed, char **err)
{
  JsonObjectIter it;
  const gchar *key;
  JsonNode *node;
  json_object_iter_init(&it, obj);
  while (json_object_iter_next(&it, &key, &node))
    if (!g_strv_contains(allowed, key))
      return pb_fail(err, key, "unknown option");
  return TRUE;
}
static JsonObject *pb_obj(JsonObject *parent, const char *key, char **err)
{
  JsonNode *n = json_object_get_member(parent, key);
  if (n && JSON_NODE_HOLDS_OBJECT(n))
    return json_node_get_object(n);
  pb_fail(err, key, "expected an object");
  return NULL;
}
static const char *pb_str(JsonObject *o, const char *key, char **err)
{
  JsonNode *n = json_object_get_member(o, key);
  if (n && json_node_get_value_type(n) == G_TYPE_STRING)
    return json_node_get_string(n);
  pb_fail(err, key, "expected a string");
  return NULL;
}
static gboolean pb_bool(JsonObject *o, const char *key, gboolean *v, char **err)
{
  JsonNode *n = json_object_get_member(o, key);
  if (!n)
    return TRUE;
  if (json_node_get_value_type(n) != G_TYPE_BOOLEAN)
    return pb_fail(err, key, "expected true or false");
  *v = json_node_get_boolean(n);
  return TRUE;
}
static gboolean pb_num(JsonNode *n, const char *key, double lo, double hi, float *v, char **err)
{
  GType t = n ? json_node_get_value_type(n) : G_TYPE_INVALID;
  if (t != G_TYPE_DOUBLE && t != G_TYPE_INT64 && t != G_TYPE_INT)
    return pb_fail(err, key, "expected a number");
  double d = json_node_get_double(n);
  if (!isfinite(d) || d < lo || d > hi)
  {
    _seterr(err, "blend.%s: expected a finite number in [%g,%g]", key, lo, hi);
    return FALSE;
  }
  *v = (float)d;
  return TRUE;
}
static gboolean pb_scalar(JsonObject *o, const char *key, double lo, double hi, float *v, char **err)
{
  return !json_object_has_member(o, key) || pb_num(json_object_get_member(o, key), key, lo, hi, v, err);
}
static const personal_option_t *pb_option(const personal_option_t *opts, int space, const char *name,
                                          int value)
{
  if (space < 1 || space > 4)
    return NULL;
  for (; opts->name; opts++)
    if ((opts->spaces & (1 << space)) && (name ? g_str_equal(name, opts->name) : opts->value == value))
      return opts;
  return NULL;
}
static int pb_space(const char *name)
{
  for (int s = 1; s <= 4; s++)
    if (!g_strcmp0(name, space_names[s]))
      return s;
  return 0;
}
static gboolean pb_space_allowed(int def, int space)
{
  return def &&
         (def == space || ((def == DEVELOP_BLEND_CS_RGB_SCENE || def == DEVELOP_BLEND_CS_RGB_DISPLAY) &&
                           (space == DEVELOP_BLEND_CS_RGB_SCENE || space == DEVELOP_BLEND_CS_RGB_DISPLAY)));
}
static JsonArray *pb_names(const personal_option_t *opts, int space, gboolean add_output)
{
  JsonArray *a = json_array_new();
  for (; opts->name; opts++)
    if (opts->spaces & (1 << space))
    {
      json_array_add_string_element(a, opts->name);
      if (add_output)
      {
        gchar *out = g_strconcat(opts->name, "_out", NULL);
        json_array_add_string_element(a, out);
        g_free(out);
      }
    }
  return a;
}
static char *pb_json(JsonObject *o)
{
  JsonNode *n = json_node_new(JSON_NODE_OBJECT);
  json_node_take_object(n, o);
  char *s = json_to_string(n, FALSE);
  json_node_unref(n);
  return s;
}

char *dt_bridge_blend_capabilities(const char *op, char **err)
{
  if (op && !_find_so(op))
  {
    _seterr(err, "unknown operation '%s'", op);
    return NULL;
  }
  JsonObject *root = json_object_new(), *spaces = json_object_new();
  for (int s = 1; s <= 4; s++)
  {
    JsonObject *row = json_object_new();
    json_object_set_array_member(row, "modes", pb_names(modes, s, FALSE));
    json_object_set_array_member(row, "channels", pb_names(channels, s, TRUE));
    json_object_set_object_member(spaces, space_names[s], row);
  }
  json_object_set_object_member(root, "spaces", spaces);
  json_object_set_string_member(root, "threshold_units",
                                "normalized native slider coordinates; four sorted edges, 0 to 1");
  json_object_set_string_member(root, "channel_update",
                                "A parametric mask replaces all mask channels. Omit mask to preserve it.");
  JsonArray *mods = json_array_new();
  dt_develop_t dev;
  dt_dev_init(&dev, FALSE);
  dev.iop = dt_iop_load_modules_ext(&dev, TRUE);
  for (GList *l = dev.iop; l; l = l->next)
  {
    dt_iop_module_t *m = l->data;
    if (op && strcmp(op, m->op))
      continue;
    JsonObject *row = json_object_new();
    JsonArray *allowed = json_array_new();
    int def = dt_develop_blend_default_module_blend_colorspace(m);
    for (int s = 1; s <= 4; s++)
      if (pb_space_allowed(def, s))
        json_array_add_string_element(allowed, space_names[s]);
    json_object_set_string_member(row, "operation", m->op);
    json_object_set_boolean_member(row, "blending", def != 0);
    json_object_set_boolean_member(row, "parametric", def >= DEVELOP_BLEND_CS_LAB);
    json_object_set_string_member(row, "default_colorspace", space_names[def]);
    json_object_set_array_member(row, "colorspaces", allowed);
    json_array_add_object_element(mods, row);
  }
  dt_dev_cleanup(&dev);
  json_object_set_array_member(root, "modules", mods);
  return pb_json(root);
}

typedef struct
{
  gboolean present[16], invert[16];
  float edges[16][4];
  gboolean is_union, invert_mask;
} personal_mask_t;

static gboolean pb_parse_mask(JsonObject *o, int space, personal_mask_t *mask, gboolean *uniform,
                              char **err)
{
  const char *const keys[] = {"type", "combine", "invert", "channels", NULL};
  if (!pb_keys(o, keys, err))
    return FALSE;
  const char *type = pb_str(o, "type", err);
  if (!type)
    return FALSE;
  if ((*uniform = g_str_equal(type, "uniform")))
    return json_object_get_size(o) == 1 || pb_fail(err, "mask", "uniform accepts only type");
  if (strcmp(type, "parametric") || space == DEVELOP_BLEND_CS_RAW)
    return pb_fail(err, "mask", "parametric requires a color blend space");
  if (json_object_has_member(o, "combine"))
  {
    const char *str = pb_str(o, "combine", err);
    if (!str)
      return FALSE;
    if (strcmp(str, "union") && strcmp(str, "intersection"))
      return pb_fail(err, "combine", "expected union or intersection");
    mask->is_union = g_str_equal(str, "union");
  }
  if (!pb_bool(o, "invert", &mask->invert_mask, err))
    return FALSE;
  JsonObject *ch = pb_obj(o, "channels", err);
  if (!ch)
    return FALSE;
  if (!json_object_get_size(ch))
    return pb_fail(err, "channels", "at least one channel is required");
  JsonObjectIter it;
  const char *name;
  JsonNode *node;
  json_object_iter_init(&it, ch);
  while (json_object_iter_next(&it, &name, &node))
  {
    gboolean output = g_str_has_suffix(name, "_out");
    gchar *base = output ? g_strndup(name, strlen(name) - 4) : g_strdup(name);
    const personal_option_t *opt = pb_option(channels, space, base, -1);
    g_free(base);
    if (!opt)
      return pb_fail(err, name, "unavailable channel for this blend colorspace; see blend_capabilities");
    int slot = opt->value + (output ? 4 : 0);
    JsonObject *range = pb_obj(ch, name, err);
    if (!range)
      return FALSE;
    const char *const fields[] = {"thresholds", "invert", NULL};
    if (!pb_keys(range, fields, err) || !pb_bool(range, "invert", &mask->invert[slot], err))
      return FALSE;
    JsonNode *t = json_object_get_member(range, "thresholds");
    if (!t || !JSON_NODE_HOLDS_ARRAY(t) || json_array_get_length(json_node_get_array(t)) != 4)
      return pb_fail(err, name, "thresholds require four ascending numbers in [0,1]");
    for (int i = 0; i < 4; i++)
    {
      if (!pb_num(json_array_get_element(json_node_get_array(t), i), name, 0, 1, &mask->edges[slot][i],
                  err))
        return FALSE;
      if (i && mask->edges[slot][i] < mask->edges[slot][i - 1])
        return pb_fail(err, name, "thresholds must be nondecreasing");
    }
    mask->present[slot] = TRUE;
  }
  return TRUE;
}

/* Use a native flexi group. Maximum and minimum are respectively the union
 * and intersection of the individual channel masks including their ramps. */
static void pb_make_mask(dt_iop_module_t *mod, dt_develop_blend_params_t *bp, const personal_mask_t *mask)
{
  dt_develop_t *dev = mod->dev;
  dt_masks_form_t *group = dt_masks_create(DT_MASKS_GROUP);
  group->formid = dt_masks_new_marker_id(dev->forms);
  g_strlcpy(group->name, "Parametric mask", sizeof(group->name));
  dev->forms = g_list_append(dev->forms, group);
  dt_masks_point_group_t *marker =
      dt_masks_marker_new(dev->forms, group, mask->is_union ? 0 : DT_MASKS_STATE_FLEXI_MINIMUM);
  if (mask->invert_mask)
    marker->state |= DT_MASKS_STATE_OP_INVERT;
  group->points = g_list_append(NULL, marker);
  const dt_iop_gui_blendif_channel_t *table = dt_develop_blendif_channels_for_csp(bp->blend_cst);
  dt_develop_blend_params_t defaults;
  dt_develop_blend_init_blend_parameters(&defaults, bp->blend_cst);
  for (int ch = 0; table[ch].label; ch++)
    for (int io = 0; io < 2; io++)
    {
      int slot = table[ch].param_channels[io];
      if (!mask->present[slot])
        continue;
      dt_masks_form_t *leaf = dt_masks_create(DT_MASKS_PARAMETRIC);
      leaf->formid = dt_masks_new_marker_id(dev->forms);
      dt_masks_point_parametric_t *p = calloc(1, sizeof(*p));
      p->colorspace = bp->blend_cst;
      p->channel = ch;
      p->in_out = io ? DT_MASKS_PARAM_VIEW_BOTH : DT_MASKS_PARAM_VIEW_INPUT;
      p->disabled = io ? 1u : 2u;
      p->blendif = (1u << slot) | (mask->invert[slot] ? (1u << (slot + 16)) : 0u);
      memcpy(p->blendif_boost_factors, defaults.blendif_boost_factors, sizeof(p->blendif_boost_factors));
      memcpy(p->blendif_parameters, defaults.blendif_parameters, sizeof(p->blendif_parameters));
      memcpy(p->blendif_parameters + 4 * slot, mask->edges[slot], 4 * sizeof(float));
      leaf->points = g_list_append(NULL, p);
      dt_masks_assign_unique_name(dev, leaf);
      dev->forms = g_list_append(dev->forms, leaf);
      dt_masks_point_group_t *member = calloc(1, sizeof(*member));
      member->formid = leaf->formid;
      member->parentid = group->formid;
      member->state = DT_MASKS_STATE_SHOW | DT_MASKS_STATE_USE | DT_MASKS_STATE_UNION;
      member->opacity = member->group_opacity = 1.0f;
      group->points = g_list_append(group->points, member);
    }
  dt_develop_blend_set_mask_group_id(mod, bp, group->formid);
}

static gboolean pb_apply(dt_iop_module_t *mod, JsonObject *o, gboolean *forms_changed, char **err)
{
  const char *const fields[] = {"colorspace", "mode", "opacity",    "reverse",
                                "fulcrum_ev", "mask", "refinement", NULL};
  if (!pb_keys(o, fields, err))
    return FALSE;
  if (!json_object_get_size(o))
    return pb_fail(err, "settings", "expected at least one setting");
  int def = dt_develop_blend_default_module_blend_colorspace(mod);
  if (!def || !mod->blend_params)
    return pb_fail(err, "module", "this operation does not support blending");
  dt_develop_blend_params_t bp = *mod->blend_params;
  int s = bp.blend_cst ? bp.blend_cst : def;
  if (json_object_has_member(o, "colorspace"))
  {
    const char *val = pb_str(o, "colorspace", err);
    if (!val)
      return FALSE;
    int next = pb_space(val);
    if (!pb_space_allowed(def, next))
      return pb_fail(err, "colorspace", "unsupported for this module; see blend_capabilities");
    if (next != s)
    {
      if (dt_is_valid_maskid(dt_develop_blend_mask_group_id(mod, &bp)) &&
          !json_object_has_member(o, "mask"))
        return pb_fail(err, "colorspace",
                       "supply an explicit replacement mask when changing the space of a masked module");
      if (!pb_option(modes, next, NULL, bp.blend_mode & DEVELOP_BLEND_MODE_MASK) &&
          !json_object_has_member(o, "mode"))
        return pb_fail(err, "mode", "select a supported mode with the new colorspace");
      s = next;
    }
  }
  bp.blend_cst = s;
  if (json_object_has_member(o, "mode"))
  {
    const char *val = pb_str(o, "mode", err);
    if (!val)
      return FALSE;
    const personal_option_t *choice = pb_option(modes, s, val, -1);
    if (!choice)
      return pb_fail(err, "mode", "unavailable for this colorspace; see blend_capabilities");
    if ((bp.blend_mode & DEVELOP_BLEND_MODE_MASK) != choice->value)
      bp.blend_parameter = 0.0f;
    bp.blend_mode = (bp.blend_mode & DEVELOP_BLEND_REVERSE) | choice->value;
  }
  if (json_object_has_member(o, "fulcrum_ev"))
  {
    const int mode = bp.blend_mode & DEVELOP_BLEND_MODE_MASK;
    const gboolean supported =
        s == DEVELOP_BLEND_CS_RGB_SCENE &&
        (mode == DEVELOP_BLEND_ADD || mode == DEVELOP_BLEND_SUBTRACT || mode == DEVELOP_BLEND_MULTIPLY ||
         mode == DEVELOP_BLEND_DIVIDE || mode == DEVELOP_BLEND_RGB_R || mode == DEVELOP_BLEND_RGB_G ||
         mode == DEVELOP_BLEND_RGB_B);
    if (!supported)
      return pb_fail(err, "fulcrum_ev", "unavailable for this mode and colorspace");
    if (!pb_scalar(o, "fulcrum_ev", -18, 18, &bp.blend_parameter, err))
      return FALSE;
  }
  gboolean reverse = (bp.blend_mode & DEVELOP_BLEND_REVERSE) != 0;
  if (!pb_bool(o, "reverse", &reverse, err) || !pb_scalar(o, "opacity", 0, 100, &bp.opacity, err))
    return FALSE;
  bp.blend_mode = (bp.blend_mode & ~DEVELOP_BLEND_REVERSE) | (reverse ? DEVELOP_BLEND_REVERSE : 0);
  if (json_object_has_member(o, "refinement"))
  {
    JsonObject *f = pb_obj(o, "refinement", err);
    if (!f)
      return FALSE;
    const char *const keys[] = {"feathering_radius", "feathering_guide", "blur_radius", "brightness",
                                "contrast",          "details",          NULL};
    if (!pb_keys(f, keys, err) || !pb_scalar(f, "feathering_radius", 0, 250, &bp.feathering_radius, err) ||
        !pb_scalar(f, "blur_radius", 0, 100, &bp.blur_radius, err) ||
        !pb_scalar(f, "brightness", -1, 1, &bp.brightness, err) ||
        !pb_scalar(f, "contrast", -1, 1, &bp.contrast, err) ||
        !pb_scalar(f, "details", -1, 1, &bp.details, err))
      return FALSE;
    if (json_object_has_member(f, "feathering_guide"))
    {
      const char *val = pb_str(f, "feathering_guide", err);
      if (!val)
        return FALSE;
      int i = 0;
      while (i < 4 && strcmp(val, guide_names[i]))
        i++;
      if (i == 4)
        return pb_fail(err, "feathering_guide", "unknown guide");
      bp.feathering_guide = guides[i];
    }
  }
  if (json_object_has_member(o, "mask"))
  {
    JsonObject *m = pb_obj(o, "mask", err);
    if (!m)
      return FALSE;
    personal_mask_t mask = {0};
    gboolean uniform = FALSE;
    if (!pb_parse_mask(m, s, &mask, &uniform, err))
      return FALSE;
    bp.mask_mode = DEVELOP_MASK_ENABLED | DEVELOP_MASK_FLEXI;
    bp.mask_combine = 0;
    bp.blendif = 0;
    dt_develop_blend_set_mask_group_id(mod, &bp, NO_MASKID);
    if (!uniform)
      pb_make_mask(mod, &bp, &mask);
    *forms_changed = TRUE;
  }
  else if (bp.mask_mode == DEVELOP_MASK_DISABLED)
    bp.mask_mode = DEVELOP_MASK_ENABLED | DEVELOP_MASK_FLEXI;
  *mod->blend_params = bp;
  return TRUE;
}
static JsonObject *pb_mask_read(GList *forms, dt_mask_id_t id, const dt_develop_blend_params_t *bp)
{
  JsonObject *mask = json_object_new();
  const char *type = (bp->mask_mode & DEVELOP_MASK_ENABLED) ? "uniform" : "disabled";
  if (bp->mask_mode & DEVELOP_MASK_RASTER)
    type = "native_raster";
  else if (bp->mask_mode & DEVELOP_MASK_CONDITIONAL)
    type = "native_conditional";
  json_object_set_string_member(mask, "type", type);
  if (!dt_is_valid_maskid(id))
    return mask;
  dt_masks_form_t *group = dt_masks_get_from_id_ext(forms, id);
  dt_masks_point_group_t *marker = group ? dt_masks_group_marker(group) : NULL;
  json_object_set_string_member(mask, "type", "native_group");
  json_object_set_int_member(mask, "group_id", id);
  if (!marker)
    return mask;
  int op = marker->state & DT_MASKS_STATE_FLEXI_OP;
  if (op != 0 && op != DT_MASKS_STATE_FLEXI_MINIMUM)
    return mask;
  JsonObject *ch = json_object_new();
  for (GList *l = group->points->next; l; l = l->next)
  {
    dt_masks_point_group_t *pt = l->data;
    dt_masks_form_t *f = dt_masks_get_from_id_ext(forms, pt->formid);
    if (!f || !(f->type & DT_MASKS_PARAMETRIC) || !f->points || f->points->next ||
        (pt->state & (DT_MASKS_STATE_HIDDEN | DT_MASKS_STATE_DISABLE | DT_MASKS_STATE_INVERSE)) ||
        pt->opacity != 1.0f || pt->refinement.enabled)
      goto complex;
    const dt_masks_point_parametric_t *p = f->points->data;
    if ((int)p->colorspace != bp->blend_cst)
      goto complex;
    for (int slot = 0; slot < 16; slot++)
      if (p->blendif & (1u << slot))
      {
        gboolean out = (slot & 4) != 0;
        const personal_option_t *opt = pb_option(channels, bp->blend_cst, NULL, slot - (out ? 4 : 0));
        if (!opt)
          goto complex;
        gchar *key = g_strconcat(opt->name, out ? "_out" : "", NULL);
        if (json_object_has_member(ch, key))
        {
          g_free(key);
          goto complex;
        }
        JsonObject *entry = json_object_new();
        JsonArray *thresholds = json_array_new();
        for (int j = 0; j < 4; j++)
          json_array_add_double_element(thresholds, p->blendif_parameters[slot * 4 + j]);
        json_object_set_array_member(entry, "thresholds", thresholds);
        json_object_set_boolean_member(entry, "invert", (p->blendif & (1u << (16 + slot))) != 0);
        json_object_set_object_member(ch, key, entry);
        g_free(key);
      }
  }
  if (!json_object_get_size(ch) || marker->group_opacity != 1.0f || marker->refinement.enabled ||
      (marker->state & DT_MASKS_STATE_OP_BYPASS))
    goto complex;
  json_object_set_string_member(mask, "type", "parametric");
  json_object_set_string_member(mask, "combine", op == 0 ? "union" : "intersection");
  json_object_set_boolean_member(mask, "invert", (marker->state & DT_MASKS_STATE_OP_INVERT) != 0);
  json_object_set_object_member(mask, "channels", ch);
  return mask;
complex:
  json_object_unref(ch);
  return mask;
}

char *dt_bridge_get_blend_json(int id, const char *op, int priority, char **err)
{
  dt_iop_module_so_t *so = op ? _find_so(op) : NULL;
  if (!so || !(so->flags() & IOP_FLAGS_SUPPORTS_BLENDING) || priority < 0)
  {
    _seterr(err, "get_blend: unsupported operation or instance");
    return NULL;
  }
  if (!_require_image(id, "get_blend", err))
    return NULL;
  sqlite3_stmt *st = NULL;
  sqlite3 *db = dt_database_get(darktable.db);
  const char *query = "SELECT h.blendop_params,h.blendop_version,i.history_end FROM main.history h "
                      "JOIN main.images i ON h.imgid=i.id WHERE h.imgid=?1 AND h.operation=?2 "
                      "AND h.multi_priority=?3 AND h.num < i.history_end ORDER BY h.num DESC LIMIT 1";
  if (sqlite3_prepare_v2(db, query, -1, &st, NULL) != SQLITE_OK)
  {
    _seterr(err, "get_blend: cannot read catalog history");
    return NULL;
  }
  sqlite3_bind_int(st, 1, id);
  sqlite3_bind_text(st, 2, op, -1, SQLITE_TRANSIENT);
  sqlite3_bind_int(st, 3, priority);
  dt_develop_blend_params_t bp;
  int end;
  if (sqlite3_step(st) != SQLITE_ROW)
  {
    sqlite3_finalize(st);
    _seterr(err, "get_blend: no committed entry for %s instance %d", op, priority);
    return NULL;
  }
  if (sqlite3_column_int(st, 1) != DEVELOP_BLEND_VERSION || sqlite3_column_bytes(st, 0) != (int)sizeof(bp))
  {
    sqlite3_finalize(st);
    _seterr(err, "get_blend: unsupported stored blend version or layout");
    return NULL;
  }
  memcpy(&bp, sqlite3_column_blob(st, 0), sizeof(bp));
  end = sqlite3_column_int(st, 2);
  sqlite3_finalize(st);
  int s = bp.blend_cst;
  JsonObject *root = json_object_new(), *b = json_object_new(), *ref = json_object_new();
  json_object_set_string_member(root, "operation", op);
  json_object_set_int_member(root, "multi_priority", priority);
  json_object_set_object_member(root, "blend", b);
  json_object_set_string_member(b, "colorspace", s >= 0 && s <= 4 ? space_names[s] : "unknown");
  const personal_option_t *mode = pb_option(modes, s, NULL, bp.blend_mode & DEVELOP_BLEND_MODE_MASK);
  json_object_set_string_member(b, "mode", mode ? mode->name : "native_other");
  json_object_set_int_member(b, "mode_id", bp.blend_mode & DEVELOP_BLEND_MODE_MASK);
  json_object_set_boolean_member(b, "reverse", (bp.blend_mode & DEVELOP_BLEND_REVERSE) != 0);
  json_object_set_double_member(b, "opacity", bp.opacity);
  json_object_set_double_member(b, "fulcrum_ev", bp.blend_parameter);
  dt_mask_id_t group = (so->flags() & IOP_FLAGS_NO_MASKS) ? bp.blend_mask_id : bp.mask_id;
  GList *forms = dt_is_valid_maskid(group) ? dt_masks_read_forms_at(id, end - 1) : NULL;
  json_object_set_object_member(b, "mask", pb_mask_read(forms, group, &bp));
  g_list_free_full(forms, (GDestroyNotify)dt_masks_free_form);
  json_object_set_double_member(ref, "feathering_radius", bp.feathering_radius);
  for (int i = 0; i < 4; i++)
    if ((int)bp.feathering_guide == guides[i])
      json_object_set_string_member(ref, "feathering_guide", guide_names[i]);
  json_object_set_double_member(ref, "blur_radius", bp.blur_radius);
  json_object_set_double_member(ref, "details", bp.details);
  json_object_set_double_member(ref, "contrast", bp.contrast);
  json_object_set_double_member(ref, "brightness", bp.brightness);
  json_object_set_object_member(b, "refinement", ref);
  return pb_json(root);
}
#undef LAB
#undef DISP
#undef SCENE
#undef RAW
#undef OLD
#undef ALL
