(ns app.ds.tabs
  (:require [app.ds.tokens :as t]))

;; Tab pattern (WAI-ARIA Authoring Practices — Tabs).
;; - Container is role=tablist
;; - Each tab is role=tab with aria-selected, aria-controls, id, and a roving
;;   tabindex (0 active / -1 inactive).
;; - ArrowLeft/ArrowRight moves focus AND activation across tabs.
;; - The companion `tab` panel sets role=tabpanel + aria-labelledby matching
;;   the tab id, plus tabindex=0 so users can scroll the panel content.

(defn- tab-id [k]
  (str "ds-tab-" (if (keyword? k) (name k) (str k))))

(defn- panel-id [k]
  (str "ds-tabpanel-" (if (keyword? k) (name k) (str k))))

(defn- index-of-key
  "Position of `current` in the tabs vector, or 0 if not found."
  [tabs current]
  (or (->> tabs
           (map-indexed (fn [idx t] [idx (:key t)]))
           (some (fn [[idx k]] (when (= k current) idx))))
      0))

(defn- handle-tab-keydown
  "Arrow-key roving focus + activation for a horizontal tablist."
  [e tabs current on-change]
  (let [k (.-key e)
        i (index-of-key tabs current)
        n (count tabs)]
    (when (and (contains? #{"ArrowLeft" "ArrowRight" "Home" "End"} k) (pos? n))
      (.preventDefault e)
      (let [next-idx (case k
                       "ArrowLeft"  (mod (dec i) n)
                       "ArrowRight" (mod (inc i) n)
                       "Home"       0
                       "End"        (dec n))
            next-key (:key (nth tabs next-idx))]
        (when on-change (on-change next-key))
        (when-let [el (js/document.getElementById (tab-id next-key))]
          (.focus el))))))

(defn tab-group
  "Tab navigation group, styled to match the design's .tabs spec.
   tabs: [{:key :overview :label \"Visão Geral\"} ...]
   active: currently active tab key
   on-change: fn called with tab key on click or arrow-key activation
   aria-label: optional accessible name for the tablist"
  [{:keys [tabs active on-change] :as props}]
  [:div {:role "tablist"
         :aria-label (:aria-label props)
         :on-key-down #(handle-tab-keydown % tabs active on-change)
         :style {:display "flex" :gap "2px"
                 :border-bottom (str "1px solid " t/border-default)
                 :margin-bottom "-1px"}}
   (for [{:keys [key label]} tabs]
     (let [selected? (= key active)]
       ^{:key key}
       [:button {:id (tab-id key)
                 :role "tab"
                 :type "button"
                 :aria-selected (if selected? "true" "false")
                 :aria-controls (panel-id key)
                 :tab-index (if selected? 0 -1)
                 :on-click #(when on-change (on-change key))
                 :style {:padding "10px 14px"
                         :font-family t/font-ui
                         :font-weight (:semibold t/font-weights)
                         :font-size "13px"
                         :color (if selected? t/text-primary t/text-tertiary)
                         :background "none"
                         :border "none"
                         :border-bottom (if selected?
                                          (str "2px solid " t/color-primary)
                                          "2px solid transparent")
                         :cursor "pointer"
                         :transition (str "color " t/transition-fast ", border-color " t/transition-fast)}}
        label]))])

(defn tab
  "Tab panel — renders children only when active. Pairs with `tab-group` via
   :tab-key (the same keyword that appears in the tab item's :key). The panel
   is focusable so users can scroll its content with the keyboard.

   Props: active?, tab-key, class.

   Note: the prop is :tab-key (not :key) because Reagent reserves :key in a
   props map for React reconciliation."
  [{:keys [active? tab-key class]} & children]
  (when active?
    (into [:div {:role "tabpanel"
                 :id (panel-id tab-key)
                 :aria-labelledby (tab-id tab-key)
                 :tab-index 0
                 :class class}]
          children)))
