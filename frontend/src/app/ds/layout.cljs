(ns app.ds.layout
  (:require [app.ds.tokens :as t]
            [re-frame.core :as rf]))

(defn sidebar-item
  [{:keys [label icon active? on-click]}]
  [:div {:style {:display "flex" :align-items "center" :gap "12px"
                 :padding "10px 16px"
                 :border-radius (:md t/border-radius)
                 :cursor "pointer"
                 :transition t/transition-fast
                 :background (if active? t/bg-surface "transparent")
                 :color (if active? t/text-primary t/text-secondary)
                 :font-weight (if active? (:semibold t/font-weights) (:regular t/font-weights))
                 :font-size (:sm t/font-sizes)}
         :on-click on-click}
   (when icon [:span icon])
   [:span label]])

(defn sidebar
  "Left sidebar navigation."
  [{:keys [items current-route user]}]
  [:nav {:style {:width "260px"
                 :min-height "100vh"
                 :background t/bg-card
                 :border-right (str "1px solid " t/border-default)
                 :padding "24px 16px"
                 :display "flex"
                 :flex-direction "column"
                 :gap "4px"}}
   ;; Logo / App name
   [:div {:style {:padding "0 16px 24px" :margin-bottom "8px"
                  :border-bottom (str "1px solid " t/border-default)}}
    [:h2 {:style {:font-size (:lg t/font-sizes) :font-weight (:bold t/font-weights) :color t/color-primary :margin "0"}}
     "Comissões"]
    [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} "Pipo Saúde"]]

   ;; Nav items
   (for [{:keys [key label icon route]} items]
     ^{:key key}
     [sidebar-item {:label label
                    :icon icon
                    :active? (= key current-route)
                    :on-click #(rf/dispatch [:navigate route])}])

   ;; Spacer
   [:div {:style {:flex "1"}}]

   ;; User info at bottom
   (when user
     [:div {:style {:padding "16px"
                    :border-top (str "1px solid " t/border-default)
                    :display "flex"
                    :align-items "center"
                    :gap "12px"}}
      [:div {:style {:width "32px" :height "32px" :border-radius (:full t/border-radius)
                     :background t/bg-surface :display "flex" :align-items "center" :justify-content "center"
                     :font-size (:xs t/font-sizes) :font-weight (:semibold t/font-weights) :color t/text-secondary}}
       (-> (:name user) first str .toUpperCase)]
      [:div {:style {:display "flex" :flex-direction "column"}}
       [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:medium t/font-weights)}} (:name user)]
       [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} (:role user)]]])])

(defn header
  "Top header with notification bell and breadcrumb."
  [{:keys [title subtitle]} & children]
  [:header {:style {:display "flex"
                    :justify-content "space-between"
                    :align-items "center"
                    :padding "24px 32px"
                    :background t/bg-card
                    :border-bottom (str "1px solid " t/border-default)}}
   [:div
    [:h1 {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights) :margin "0" :color t/text-primary}} title]
    (when subtitle
      [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary}} subtitle])]
   (into [:div {:style {:display "flex" :align-items "center" :gap "16px"}}] children)])

(defn page-shell
  "Main page layout: sidebar + header + content."
  [{:keys [sidebar-items current-route user title subtitle header-actions]} & children]
  [:div {:style {:display "flex" :min-height "100vh" :background t/bg-main}}
   ;; Sidebar
   [sidebar {:items sidebar-items :current-route current-route :user user}]
   ;; Main content
   [:div {:style {:flex "1" :display "flex" :flex-direction "column"}}
    [header {:title title :subtitle subtitle}
     header-actions]
    (into [:main {:style {:flex "1" :padding "32px" :overflow-y "auto"}}]
          children)]])
