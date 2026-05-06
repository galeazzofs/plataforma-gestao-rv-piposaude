(ns app.ds.layout
  (:require [re-frame.core :as rf]
            [reitit.frontend.easy :as rfe]
            [clojure.string :as str]
            [app.ds.nav :as nav]))

;; ============================================
;; Pipo design shell — sidebar + topbar + page-shell.
;; Render the same HTML markup used by the design (.app/.sidebar/.brand/.nav/
;; .topbar/.page) so all the rules in pipo-design.css apply.
;;
;; A11y: landmark roles via semantic elements (<aside>, <nav>, <main>),
;; aria-label on regions, aria-current on active nav, skip-to-content link.
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
    [:div.avatar {:aria-hidden true}
     (or (some-> first-letter str/upper-case) "?")]))

(defn- safe-href
  "Resolve a route name to a URL via reitit. Falls back to # if the route is
   not registered (avoids hard crashes during development)."
  [route]
  (try (rfe/href route) (catch :default _ "#")))

(defn nav-item-link
  "Single sidebar nav-item — either a route link or a section header."
  [{:keys [item active-key]}]
  (cond
    (:section item)
    [:div.nav-section {:role "presentation"} (:section item)]

    :else
    (let [active? (= (:key item) active-key)
          route   (:route item)
          href    (safe-href route)
          label   (:label item)]
      ;; aria-label carries the label text even when the visible <span>
      ;; collapses (e.g. icons-only sidebar on mobile). title makes it a
      ;; mouse-hover tooltip in the same case.
      [:a (cond-> {:class (str "nav-item" (when active? " active"))
                   :href href
                   :title label
                   :aria-label label
                   :on-click (fn [e]
                               (.preventDefault e)
                               (rf/dispatch [:navigate route]))}
            active? (assoc :aria-current "page"))
       [icon (:icon item) {:width 18 :height 18}]
       [:span {:style {:flex 1}} label]
       (when (:badge item)
         [:span.badge {:aria-label (str "Pendentes: " (:badge item))}
          (:badge item)])])))

(defn sidebar
  "Left sidebar.
   Props: items (vector of nav items / sections), active-key, user."
  [{:keys [items active-key user]}]
  [:aside.sidebar {:aria-label "Navegação principal"}
   [:div.brand
    [:div.brand-mark {:aria-hidden true} "P"]
    [:div.brand-name
     [:strong "Pipo Saúde"]
     [:span "plataforma · rv"]]]
   [:nav.nav {:aria-label "Seções"}
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
  "Pipo search pill. opts: {:placeholder ... :value ... :on-change ... :aria-label ...}"
  [{:keys [placeholder value on-change] :as props}]
  (let [label (or (:aria-label props) placeholder "Buscar")]
    [:div.search {:role "search"}
     [icon "search" {:width 14 :height 14}]
     [:input {:placeholder (or placeholder "Buscar")
              :aria-label label
              :value (or value "")
              :on-change (fn [e]
                           (when on-change
                             (on-change (.. e -target -value))))}]]))

(defn icon-btn
  "Topbar icon button. opts: {:icon \"bell\" :on-click ... :dot? true :aria-label ...}"
  [{:keys [icon on-click dot? aria-label]}]
  [:button.icon-btn {:type "button"
                     :on-click on-click
                     :aria-label aria-label}
   [app.ds.layout/icon icon {:width 16 :height 16}]
   (when dot?
     [:span.dot {:aria-hidden true}])])

(defn- breadcrumbs [crumbs]
  (when (seq crumbs)
    [:nav {:aria-label "Trilha"
           :class "crumbs"}
     (for [[idx c] (map-indexed vector crumbs)]
       ^{:key idx} [:span c])]))

(defn topbar
  "Topbar with crumbs, title, subtitle and right-side actions.
   Props: crumbs (seq), title, subtitle, actions (vector of hiccup children
   to splice into .topbar-r)."
  [{:keys [crumbs title subtitle actions]}]
  [:header.topbar
   [:div.topbar-l
    (breadcrumbs crumbs)
    [:div.title-row
     [:h1 title]
     (when subtitle [:span.subtitle subtitle])]]
   ;; Splice each action element so Reagent treats them as siblings;
   ;; passing the whole vector as a child makes Reagent try to call the
   ;; first element as a component (PersistentVector -> Invalid arity: 2).
   (into [:div.topbar-r] (cond
                           (nil? actions)        nil
                           (and (vector? actions)
                                (keyword? (first actions))) [actions]
                           :else                 actions))])

(defn skip-link
  "Visually-hidden skip-to-content link, revealed on focus. Renders as the
   first focusable element on every page."
  []
  [:a.skip-link {:href "#main-content"} "Pular para o conteúdo"])

(defn page-shell
  "Main page wrapper.
   Props: sidebar-items (overrides default), current-route, user, title,
          subtitle, crumbs, header-actions (hiccup vector to render in topbar-r).
   Children become the contents of the .page area."
  [{:keys [sidebar-items current-route user title subtitle crumbs header-actions]}
   & children]
  (let [items (or sidebar-items (nav/items-for-role (:role user)))]
    [:div.app
     [skip-link]
     [sidebar {:items items :active-key current-route :user user}]
     [:main.main {:id "main-content" :tab-index -1}
      [:section.view.active
       [topbar {:crumbs crumbs :title title :subtitle subtitle :actions header-actions}]
       (into [:div.page] children)]]]))

;; --- Compatibility re-exports for legacy callers --------------------------------

(defn header
  "Legacy header signature — forwards to topbar."
  [{:keys [title subtitle crumbs]} & children]
  [topbar {:title title :subtitle subtitle :crumbs crumbs :actions (vec children)}])
