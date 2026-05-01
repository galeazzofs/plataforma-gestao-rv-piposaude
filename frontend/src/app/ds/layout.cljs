(ns app.ds.layout
  (:require [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.nav :as nav]))

;; ============================================
;; Pipo design shell — sidebar + topbar + page-shell.
;; Render the same HTML markup used by the design (.app/.sidebar/.brand/.nav/
;; .topbar/.page) so all the rules in pipo-design.css apply.
;; ============================================

(defn icon
  "Inline SVG icon, referencing a <symbol> defined in index.html.
   Accepts a name like \"money\" or \":money\" or \"i-money\"."
  ([name] (icon name nil))
  ([name {:keys [width height class]}]
   (let [s (cond (keyword? name) (clojure.core/name name)
                 :else            name)
         id (cond
              (str/starts-with? s "i-") s
              :else (str "i-" s))]
     [:svg (cond-> {:width (or width 16) :height (or height 16) :aria-hidden true}
             class (assoc :class class))
      [:use {:href (str "#" id)}]])))

(defn- avatar-of [user]
  (let [n (or (:name user) "")
        first-letter (when (seq n) (subs n 0 1))]
    [:div.avatar (or (some-> first-letter str/upper-case) "?")]))

(defn nav-item-link
  "Single sidebar nav-item — either a route link or a section header."
  [{:keys [item active-key]}]
  (cond
    (:section item)
    [:div.nav-section (:section item)]

    :else
    (let [active? (= (:key item) active-key)]
      [:a {:class (str "nav-item" (when active? " active"))
           :href "#"
           :on-click (fn [e]
                       (.preventDefault e)
                       (rf/dispatch [:navigate (:route item)]))}
       [icon (:icon item) {:width 18 :height 18}]
       [:span {:style {:flex 1}} (:label item)]
       (when (:badge item)
         [:span.badge (:badge item)])])))

(defn sidebar
  "Left sidebar.
   Props: items (vector of nav items / sections), active-key, user."
  [{:keys [items active-key user]}]
  [:aside.sidebar
   [:div.brand
    [:div.brand-mark "P"]
    [:div.brand-name
     [:strong "Pipo Saúde"]
     [:span "plataforma · rv"]]]
   [:div.nav
    (for [[idx item] (map-indexed vector items)]
      ^{:key (or (:key item) (str "sec-" idx))}
      [nav-item-link {:item item :active-key active-key}])]
   (when user
     [:div.sidebar-foot
      [avatar-of user]
      [:div.user-meta
       [:strong (:name user)]
       [:span (some-> (:role user) str/lower-case (str " · pipo"))]]])])

(defn search-input
  "Pipo search pill. opts: {:placeholder ... :value ... :on-change ...}"
  [{:keys [placeholder value on-change]}]
  [:div.search
   [icon "search" {:width 14 :height 14}]
   [:input {:placeholder (or placeholder "Buscar")
            :value (or value "")
            :on-change (fn [e]
                         (when on-change
                           (on-change (.. e -target -value))))}]])

(defn icon-btn
  "Topbar icon button. opts: {:icon \"bell\" :on-click ... :dot? true}"
  [{:keys [icon on-click dot? aria-label]}]
  [:button.icon-btn {:on-click on-click :aria-label aria-label}
   [app.ds.layout/icon icon {:width 16 :height 16}]
   (when dot? [:span.dot])])

(defn topbar
  "Topbar with crumbs, title, subtitle and right-side actions.
   Props: crumbs (seq), title, subtitle, actions (hiccup)."
  [{:keys [crumbs title subtitle actions]}]
  [:header.topbar
   [:div.topbar-l
    (when (seq crumbs)
      (into [:div.crumbs] (for [c crumbs] [:span c])))
    [:div.title-row
     [:h1 title]
     (when subtitle [:span.subtitle subtitle])]]
   [:div.topbar-r actions]])

(defn page-shell
  "Main page wrapper.
   Props: sidebar-items (overrides default), current-route, user, title,
          subtitle, crumbs, header-actions (hiccup vector to render in topbar-r).
   Children become the contents of the .page area."
  [{:keys [sidebar-items current-route user title subtitle crumbs header-actions]}
   & children]
  (let [items (or sidebar-items (nav/items-for-role (:role user)))]
    [:div.app
     [sidebar {:items items :active-key current-route :user user}]
     [:main.main
      [:section.view.active
       [topbar {:crumbs crumbs :title title :subtitle subtitle :actions header-actions}]
       (into [:div.page] children)]]]))

;; --- Compatibility re-exports for legacy callers --------------------------------

(defn header
  "Legacy header signature — forwards to topbar."
  [{:keys [title subtitle crumbs]} & children]
  [topbar {:title title :subtitle subtitle :crumbs crumbs :actions (vec children)}])
