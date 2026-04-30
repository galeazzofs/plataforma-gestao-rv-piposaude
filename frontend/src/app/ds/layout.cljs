(ns app.ds.layout
  (:require [app.ds.tokens :as t]
            [re-frame.core :as rf]
            [reagent.core :as r]
            [clojure.string :as str]))

;; ============================================
;; Pipo design shell — sidebar + topbar + page-shell.
;; Mirrors the layout from the "Todas as Telas" handoff while keeping the
;; existing sidebar-items contract used across views (key/label/icon/route).
;; ============================================

;; Legacy emoji glyphs used by views' :icon fields are mapped to the Pipo
;; design's monochrome SVG symbol set defined in index.html. New code should
;; pass keywords (e.g. :dashboard) instead of emojis.
(def ^:private emoji->symbol
  {"📊" "i-dashboard"  "📈" "i-trend"      "🏠" "i-dashboard"
   "📅" "i-clock"      "✓"  "i-check"     "✔" "i-check"
   "💰" "i-money"      "🎯" "i-target"
   "👤" "i-users"      "👥" "i-team"
   "📄" "i-doc"        "📁" "i-upload"     "📋" "i-list"
   "⚙" "i-cog"        "⚙️" "i-cog"
   "⚠" "i-alert"      "⚠️" "i-alert"      "!" "i-alert"
   "🔄" "i-refresh"    "↻" "i-refresh"
   "🧮" "i-percent"    "%" "i-percent"})

(defn- svg-icon
  "Renders a sidebar/topbar icon. Accepts:
   - keyword like :i-dashboard / :dashboard -> <use href=\"#i-...\">
   - string starting with \"i-\" -> same
   - emoji string in the legacy map -> mapped to its design symbol
   - other plain string -> rendered as text (last-resort fallback)
   - a hiccup vector -> rendered as-is"
  [icon size]
  (cond
    (vector? icon) icon
    (or (keyword? icon) (string? icon))
    (let [s (if (keyword? icon) (name icon) icon)
          symbol-id (cond
                      (str/starts-with? s "i-") s
                      (contains? emoji->symbol s) (get emoji->symbol s)
                      (re-matches #"[a-z][a-z0-9-]+" s) (str "i-" s)
                      :else nil)]
      (if symbol-id
        [:svg {:width size :height size :aria-hidden true
               :style {:flex-shrink 0}}
         [:use {:href (str "#" symbol-id)}]]
        [:span {:style {:font-size (str size "px") :line-height "1"}} s]))
    :else nil))

(defn- nav-item
  [{:keys [label icon active? on-click badge]}]
  (let [hovered? (r/atom false)]
    (fn [{:keys [label icon active? on-click badge]}]
      [:div {:style (cond-> {:display "flex" :align-items "center" :gap "10px"
                             :padding "8px 12px"
                             :border-radius (:sm t/border-radius)
                             :cursor "pointer" :user-select "none"
                             :font-family t/font-ui
                             :font-size "13.5px"
                             :font-weight (if active? (:semibold t/font-weights) (:medium t/font-weights))
                             :color (if active? t/text-primary t/text-secondary)
                             :background (cond
                                           active?   t/beige-100
                                           @hovered? t/bg-main
                                           :else     "transparent")
                             :border-left (if active?
                                            (str "2px solid " t/color-primary)
                                            "2px solid transparent")
                             :transition (str "background " t/transition-fast ", color " t/transition-fast)})
             :on-mouse-enter #(reset! hovered? true)
             :on-mouse-leave #(reset! hovered? false)
             :on-click on-click}
       [:span {:style {:width "18px" :height "18px" :flex-shrink "0"
                       :display "inline-flex" :align-items "center" :justify-content "center"
                       :color (if active? t/text-primary t/text-tertiary)}}
        (svg-icon icon 18)]
       [:span {:style {:flex 1 :white-space "nowrap" :overflow "hidden" :text-overflow "ellipsis"}}
        label]
       (when badge
         [:span {:style {:font-family t/font-mono :font-size "11px" :font-weight "600"
                         :background t/error-light :color t/error-dark
                         :padding "1px 6px" :border-radius (:full t/border-radius)}}
          badge])])))

(defn- sidebar-section-label [text]
  [:div {:style {:font-family t/font-mono :font-size "10px"
                 :text-transform "uppercase" :letter-spacing "0.08em"
                 :color t/text-disabled
                 :padding "14px 12px 6px"}}
   text])

(defn sidebar
  "Left sidebar navigation.
   items can be either a flat list of {:key :label :icon :route :badge}
   or a list with section markers: {:section \"OPERAÇÃO\"} interleaved."
  [{:keys [items current-route user]}]
  [:nav {:style {:width "240px" :height "100vh" :flex-shrink "0"
                 :background t/bg-card
                 :border-right (str "1px solid " t/border-default)
                 :position "sticky" :top 0
                 :display "flex" :flex-direction "column"
                 :font-family t/font-body}}
   ;; Brand
   [:div {:style {:padding "22px 20px 18px"
                  :border-bottom (str "1px solid " t/border-default)
                  :display "flex" :gap "12px" :align-items "center"}}
    [:div {:style {:width "34px" :height "34px" :border-radius "10px"
                   :background t/color-primary :color t/color-white
                   :display "flex" :align-items "center" :justify-content "center"
                   :font-family t/font-display :font-size "22px" :line-height 1}}
     "P"]
    [:div {:style {:display "flex" :flex-direction "column" :gap "1px"}}
     [:strong {:style {:font-family t/font-heading :font-size "15px" :font-weight (:semibold t/font-weights)
                       :color t/text-primary :letter-spacing "-0.01em"}}
      "Pipo Saúde"]
     [:span {:style {:font-family t/font-mono :font-size "10px" :color t/text-tertiary
                     :letter-spacing "0.04em" :text-transform "lowercase"}}
      "comissões"]]]

   ;; Items
   [:div {:style {:flex 1 :padding "14px 12px" :overflow-y "auto"
                  :display "flex" :flex-direction "column" :gap "2px"}}
    (for [[idx item] (map-indexed vector items)]
      ^{:key (or (:key item) (str "section-" idx))}
      (cond
        (:section item)
        [sidebar-section-label (:section item)]

        :else
        [nav-item {:label    (:label item)
                   :icon     (:icon item)
                   :active?  (= (:key item) current-route)
                   :badge    (:badge item)
                   :on-click #(rf/dispatch [:navigate (:route item)])}]))]

   ;; Footer with user identity
   (when user
     [:div {:style {:padding "14px 16px"
                    :border-top (str "1px solid " t/border-default)
                    :display "flex" :align-items "center" :gap "10px"}}
      [:div {:style {:width "34px" :height "34px" :border-radius "50%"
                     :background t/beige-300 :color t/text-secondary
                     :display "flex" :align-items "center" :justify-content "center"
                     :font-family t/font-ui :font-size "13px" :font-weight (:bold t/font-weights)
                     :flex-shrink "0"}}
       (-> (:name user "?") first str .toUpperCase)]
      [:div {:style {:display "flex" :flex-direction "column" :min-width 0}}
       [:strong {:style {:font-family t/font-ui :font-size "13px"
                         :color t/text-primary :font-weight (:semibold t/font-weights)
                         :white-space "nowrap" :overflow "hidden" :text-overflow "ellipsis"}}
        (:name user)]
       [:span {:style {:font-family t/font-mono :font-size "11px" :color t/text-tertiary}}
        (:role user)]]])])

(defn- icon-btn
  "Pill icon button used in topbar (notifications, etc.)."
  [{:keys [icon on-click dot? aria-label]}]
  [:button {:on-click on-click :aria-label aria-label
            :style {:width "36px" :height "36px" :border-radius (:full t/border-radius)
                    :background t/bg-card :border (str "1px solid " t/border-default)
                    :display "inline-flex" :align-items "center" :justify-content "center"
                    :color t/text-secondary :position "relative" :cursor "pointer"
                    :transition (str "box-shadow " t/transition-fast)}}
   [:span {:style {:width "16px" :height "16px" :display "inline-flex"}}
    (svg-icon icon 16)]
   (when dot?
     [:span {:style {:position "absolute" :top "8px" :right "8px"
                     :width "7px" :height "7px" :border-radius "50%"
                     :background t/error-default
                     :border (str "1.5px solid " t/bg-card)}}])])

(defn- search-pill []
  [:div {:style {:display "flex" :align-items "center" :gap "8px"
                 :background t/bg-main :border (str "1px solid " t/border-default)
                 :padding "7px 12px" :border-radius (:full t/border-radius)
                 :width "260px" :font-size "13px" :color t/text-tertiary}}
   [:span {:style {:width "14px" :height "14px" :display "inline-flex" :color t/text-tertiary}}
    (svg-icon :search 14)]
   [:input {:placeholder "Buscar"
            :style {:flex 1 :border 0 :outline 0 :background "transparent"
                    :color t/text-primary :font-family t/font-body :font-size "13px"}}]])

(defn- crumbs-row [crumbs]
  (when (seq crumbs)
    [:div {:style {:display "flex" :align-items "center" :gap "6px"
                   :font-family t/font-mono :font-size "11px"
                   :color t/text-tertiary :text-transform "lowercase"}}
     (interpose
       [:span {:style {:color t/text-disabled :margin "0 2px"}} "/"]
       (for [c crumbs] ^{:key c} [:span c]))]))

(defn header
  "Topbar with breadcrumbs, display title, optional subtitle and right-side
   action children (search/icons/buttons). When no children are supplied, the
   default search + bell + cog cluster is rendered."
  [{:keys [title subtitle crumbs]} & children]
  [:header {:style {:display "flex" :align-items "center" :justify-content "space-between"
                    :background t/bg-card
                    :border-bottom (str "1px solid " t/border-default)
                    :padding "18px 32px" :min-height "72px"
                    :position "sticky" :top 0 :z-index 10}}
   [:div {:style {:display "flex" :flex-direction "column" :gap "2px"}}
    [crumbs-row (or crumbs ["pipo" "rv"])]
    [:div {:style {:display "flex" :align-items "baseline" :gap "14px"}}
     [:h1 {:style {:font-family t/font-display :font-weight "400"
                   :font-size "30px" :line-height "1"
                   :letter-spacing "-0.005em" :color t/text-primary
                   :margin 0}}
      title]
     (when subtitle
       [:span {:style {:font-size "13px" :color t/text-tertiary}} subtitle])]]
   (into [:div {:style {:display "flex" :align-items "center" :gap "10px"}}]
         (if (seq children)
           children
           [[search-pill]
            [icon-btn {:icon :bell :aria-label "Notificações" :dot? true}]
            [icon-btn {:icon :cog  :aria-label "Configurações"}]]))])

(defn page-shell
  "Main page layout: sidebar + header + content."
  [{:keys [sidebar-items current-route user title subtitle crumbs header-actions]} & children]
  [:div {:style {:display "grid" :grid-template-columns "240px 1fr"
                 :min-height "100vh" :background t/bg-main}}
   [sidebar {:items sidebar-items :current-route current-route :user user}]
   [:div {:style {:display "flex" :flex-direction "column" :min-width 0
                  :background t/bg-main}}
    (if (vector? header-actions)
      [header {:title title :subtitle subtitle :crumbs crumbs}
       header-actions]
      [header {:title title :subtitle subtitle :crumbs crumbs}])
    (into [:main {:style {:flex 1 :padding "28px 32px 80px"
                          :display "flex" :flex-direction "column" :gap "24px"
                          :max-width "1480px"}}]
          children)]])
