(ns app.ds.inputs
  (:require [app.ds.tokens :as t]
            [app.ds.typography :as typo]))

(defn input
  "Text input.
   Props: value, on-change, placeholder, type, error, disabled, label, required."
  [{:keys [value on-change placeholder type error disabled label required name]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
   (when label
     [typo/label {:required required} label])
   [:input {:style {:font-family t/font-family
                    :font-size (:sm t/font-sizes)
                    :padding "0 12px"
                    :height "40px"
                    :border (str "1px solid " (if error t/error-default t/border-default))
                    :border-radius (:md t/border-radius)
                    :background (if disabled t/bg-main t/bg-card)
                    :color (if disabled t/text-disabled t/text-primary)
                    :outline "none"
                    :transition (str "border-color " t/transition-fast)
                    :width "100%"
                    :box-sizing "border-box"}
            :type (or type "text")
            :value (or value "")
            :name name
            :placeholder placeholder
            :disabled disabled
            :on-change #(when on-change (on-change (.. % -target -value)))}]
   (when error
     [:span {:style {:font-size (:xs t/font-sizes) :color t/error-default}} error])])

(defn select
  "Select dropdown.
   options: [{:value \"x\" :label \"X\"} ...]"
  [{:keys [value on-change options label required disabled error]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
   (when label
     [typo/label {:required required} label])
   [:select {:style {:font-family t/font-family
                     :font-size (:sm t/font-sizes)
                     :padding "0 12px"
                     :height "40px"
                     :border (str "1px solid " (if error t/error-default t/border-default))
                     :border-radius (:md t/border-radius)
                     :background t/bg-card
                     :color t/text-primary
                     :width "100%"
                     :cursor "pointer"
                     :outline "none"
                     :appearance "auto"}
             :value (or value "")
             :disabled disabled
             :on-change #(when on-change (on-change (.. % -target -value)))}
    (for [{:keys [value label]} options]
      ^{:key value}
      [:option {:value value} label])]])

(defn file-upload
  "File upload input for XLSX.
   Props: on-file, accept, label."
  [{:keys [on-file accept label]}]
  [:div {:style {:display "flex" :flex-direction "column" :gap "6px"}}
   (when label
     [typo/label {} label])
   [:label {:style {:display "flex"
                    :align-items "center"
                    :justify-content "center"
                    :padding "32px 24px"
                    :border (str "2px dashed " t/border-default)
                    :border-radius (:lg t/border-radius)
                    :background t/bg-main
                    :cursor "pointer"
                    :transition (str "all " t/transition-fast)
                    :text-align "center"}}
    [:input {:type "file"
             :accept (or accept ".xlsx,.xls")
             :style {:display "none"}
             :on-change #(when on-file
                           (let [file (-> % .-target .-files (aget 0))]
                             (when file (on-file file))))}]
    [:div {:style {:display "flex" :flex-direction "column" :gap "6px" :align-items "center"}}
     [:span {:style {:font-size "28px"}} "📂"]
     [:span {:style {:font-size (:sm t/font-sizes) :color t/text-primary :font-weight (:medium t/font-weights)}} "Clique ou arraste o arquivo aqui"]
     [:span {:style {:font-size (:xs t/font-sizes) :color t/text-disabled}} "Formatos aceitos: .xlsx, .xls"]]]])
