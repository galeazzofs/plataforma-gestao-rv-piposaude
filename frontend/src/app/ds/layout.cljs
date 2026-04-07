(ns app.ds.layout
  (:require [app.ds.tokens :as t]
            [re-frame.core :as rf]
            [reagent.core :as r]))

(defn sidebar-item
  [{:keys [label icon active? on-click]}]
  (let [hovered? (r/atom false)]
    (fn [{:keys [label icon active? on-click]}]
      [:div {:style {:display "flex" :align-items "center" :gap "10px"
                     :padding "9px 14px"
                     :border-radius (:md t/border-radius)
                     :cursor "pointer"
                     :transition (str "all " t/transition-default)
                     :background (cond
                                   active?   t/beige-100
                                   @hovered? t/bg-hover
                                   :else     "transparent")
                     :color (if active? t/color-primary t/text-secondary)
                     :font-weight (if active? (:semibold t/font-weights) (:regular t/font-weights))
                     :font-size (:sm t/font-sizes)
                     :border-left (if active? (str "3px solid " t/color-primary) "3px solid transparent")}
             :on-mouse-enter #(reset! hovered? true)
             :on-mouse-leave #(reset! hovered? false)
             :on-click on-click}
       (when icon [:span {:style {:font-size "16px" :line-height "1"}} icon])
       [:span label]])))

(defn sidebar
  "Left sidebar navigation."
  [{:keys [items current-route user]}]
  [:nav {:style {:width "256px"
                 :min-height "100vh"
                 :background t/bg-card
                 :border-right (str "1px solid " t/border-default)
                 :padding "0"
                 :display "flex"
                 :flex-direction "column"
                 :flex-shrink "0"}}
   ;; Logo / App name
   [:div {:style {:padding "24px 20px 20px"
                  :border-bottom (str "1px solid " t/border-default)}}
    [:div {:style {:display "flex" :align-items "center" :gap "10px"}}
     [:div {:style {:width "32px" :height "32px" :border-radius (:md t/border-radius)
                    :background t/color-primary :display "flex" :align-items "center"
                    :justify-content "center"}}
      [:span {:style {:color t/color-white :font-size (:xs t/font-sizes) :font-weight (:bold t/font-weights)}} "P"]]
     [:div
      [:div {:style {:font-size (:base t/font-sizes) :font-weight (:bold t/font-weights) :color t/color-primary :line-height "1.2"}} "Pipo"]
      [:div {:style {:font-size (:xs t/font-sizes) :color t/text-disabled :letter-spacing "0.04em"}} "COMISSÕES"]]]]

   ;; Nav items
   [:div {:style {:flex "1" :padding "12px 12px" :display "flex" :flex-direction "column" :gap "2px"}}
    (for [{:keys [key label icon route]} items]
      ^{:key key}
      [sidebar-item {:label label
                     :icon icon
                     :active? (= key current-route)
                     :on-click #(rf/dispatch [:navigate route])}])]

   ;; User info at bottom
   (when user
     [:div {:style {:padding "16px 20px"
                    :border-top (str "1px solid " t/border-default)
                    :display "flex"
                    :align-items "center"
                    :gap "10px"}}
      [:div {:style {:width "34px" :height "34px" :border-radius (:full t/border-radius)
                     :background t/beige-300 :display "flex" :align-items "center" :justify-content "center"
                     :font-size (:xs t/font-sizes) :font-weight (:bold t/font-weights) :color t/beige-700
                     :flex-shrink "0"}}
       (-> (:name user "?") first str .toUpperCase)]
      [:div {:style {:display "flex" :flex-direction "column" :min-width "0"}}
       [:span {:style {:font-size (:sm t/font-sizes) :font-weight (:semibold t/font-weights) :color t/text-primary
                       :white-space "nowrap" :overflow "hidden" :text-overflow "ellipsis"}} (:name user)]
       [:span {:style {:font-size (:xs t/font-sizes) :color t/text-secondary}} (:role user)]]])])

(defn header
  "Top header with title, subtitle, and optional action children."
  [{:keys [title subtitle]} & children]
  [:header {:style {:display "flex"
                    :justify-content "space-between"
                    :align-items "center"
                    :padding "20px 32px"
                    :background t/bg-card
                    :border-bottom (str "1px solid " t/border-default)
                    :min-height "72px"}}
   [:div
    [:h1 {:style {:font-size (:2xl t/font-sizes) :font-weight (:bold t/font-weights)
                  :margin "0" :color t/text-primary :line-height "1.2"}} title]
    (when subtitle
      [:span {:style {:font-size (:sm t/font-sizes) :color t/text-secondary :margin-top "2px" :display "block"}} subtitle])]
   (into [:div {:style {:display "flex" :align-items "center" :gap "12px"}}] children)])

(defn page-shell
  "Main page layout: sidebar + header + content."
  [{:keys [sidebar-items current-route user title subtitle header-actions]} & children]
  [:div {:style {:display "flex" :min-height "100vh" :background t/bg-main}}
   ;; Sidebar
   [sidebar {:items sidebar-items :current-route current-route :user user}]
   ;; Main content
   [:div {:style {:flex "1" :display "flex" :flex-direction "column" :min-width "0"}}
    [header {:title title :subtitle subtitle}
     header-actions]
    (into [:main {:style {:flex "1" :padding "32px" :overflow-y "auto"
                          :display "flex" :flex-direction "column" :gap "24px"}}]
          children)]])
