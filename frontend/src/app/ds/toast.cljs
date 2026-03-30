(ns app.ds.toast
  (:require [app.ds.tokens :as t]
            [re-frame.core :as rf]
            [reagent.core :as r]))

(defn toast-icon [type]
  (case type
    :success "✓"
    :error   "✕"
    :warning "!"
    "i"))

(defn toast-colors [type]
  (case type
    :success {:background t/success-light :color t/success-dark :border t/success-default}
    :error   {:background t/error-light   :color t/error-dark   :border t/error-default}
    :warning {:background t/warning-light :color t/warning-dark :border t/warning-default}
    {:background t/bg-subtle :color t/text-primary :border t/border-default}))

(defn toast
  "Single toast notification.
   Props: type (:success :error :warning :info), message, on-close"
  [{:keys [type message on-close]}]
  (let [{:keys [background color border]} (toast-colors type)]
    [:div {:style {:display "flex"
                   :align-items "center"
                   :gap "12px"
                   :padding "12px 16px"
                   :background background
                   :color color
                   :border (str "1px solid " border)
                   :border-radius (:md t/border-radius)
                   :box-shadow (:md t/shadows)
                   :min-width "300px"
                   :max-width "480px"}}
     [:span {:style {:font-size "16px" :font-weight (:bold t/font-weights)}}
      (toast-icon type)]
     [:span {:style {:flex "1" :font-size (:sm t/font-sizes) :font-family t/font-family}}
      message]
     [:button {:style {:background "none" :border "none" :cursor "pointer"
                       :color color :padding "2px" :font-size "14px"}
               :on-click on-close}
      "✕"]]))

(defn toast-container
  "Container for toast notifications — subscribes to :ui/toast from re-frame db."
  []
  (let [toast-data @(rf/subscribe [:ui/toast])]
    (when toast-data
      [:div {:style {:position "fixed"
                     :bottom "24px"
                     :right "24px"
                     :z-index "2000"}}
       [toast {:type     (:type toast-data)
               :message  (:message toast-data)
               :on-close #(rf/dispatch [:ui/clear-toast])}]])))
